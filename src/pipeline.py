"""Local Cassandra → Spark → MongoDB pipeline for the IND320 notebook."""

from datetime import datetime, timezone
import os

import pandas as pd

KEYSPACE = "ind320"
TABLE = "physical_flows"
MONGO_DATABASE = "ind320"
MONGO_COLLECTION = "flows_daily"


def prepare_cassandra(host: str = "127.0.0.1", port: int = 9042):
    """Create a reproducible local keyspace/table and check CQL connectivity."""
    import socket

    # Report a stopped server before the driver starts its own connection retry.
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError as exc:
        raise ConnectionError(
            f"Cassandra is not reachable at {host}:{port}. Start the local "
            "Cassandra service and check CASSANDRA_HOST/CASSANDRA_PORT."
        ) from exc
    from cassandra.cluster import Cluster
    cluster = Cluster([host], port=port)
    try:
        session = cluster.connect()
        session.execute(
            f"CREATE KEYSPACE IF NOT EXISTS {KEYSPACE} WITH replication = "
            "{'class': 'SimpleStrategy', 'replication_factor': 1}"
        )
        session.execute(
            f"CREATE TABLE IF NOT EXISTS {KEYSPACE}.{TABLE} ("
            "connection text, direction text, year int, ts_utc timestamp, "
            "quantity_mw double, duration_hours double, "
            "PRIMARY KEY ((connection, direction, year), ts_utc))"
        )
        session.execute(f"SELECT * FROM {KEYSPACE}.{TABLE} LIMIT 1")
    finally:
        cluster.shutdown()


def start_spark(host: str = "127.0.0.1", port: int = 9042):
    """Start local Spark with the Scala/Spark-compatible Cassandra connector."""
    from pyspark.sql import SparkSession

    package = os.getenv("SPARK_CONNECTOR_PACKAGE",
                        "com.datastax.spark:spark-cassandra-connector_2.12:3.5.1")
    return (SparkSession.builder
            .appName("IND320 Cross-border flows")
            .master("local[*]")
            .config("spark.jars.packages", package)
            .config("spark.cassandra.connection.host", host)
            .config("spark.cassandra.connection.port", str(port))
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate())


def write_to_cassandra(spark, raw: pd.DataFrame):
    """Insert API points with Spark; primary keys make repeat runs idempotent."""
    from pyspark.sql.types import (DoubleType, IntegerType, StringType,
                                   StructField, StructType, TimestampType)

    schema = StructType([
        StructField("connection", StringType(), False),
        StructField("direction", StringType(), False),
        StructField("year", IntegerType(), False),
        StructField("ts_utc", TimestampType(), False),
        StructField("quantity_mw", DoubleType(), False),
        StructField("duration_hours", DoubleType(), False),
    ])
    rows = [
        (str(row.connection), str(row.direction), int(row.timestamp_utc.year),
         row.timestamp_utc.to_pydatetime().astimezone(timezone.utc).replace(tzinfo=None),
         float(row.quantity_mw), float(row.duration_hours))
        for row in raw.itertuples(index=False)
    ]
    frame = spark.createDataFrame(rows, schema=schema)
    frame.write.format("org.apache.spark.sql.cassandra").options(
        keyspace=KEYSPACE, table=TABLE).mode("append").save()
    return len(rows)


def read_and_curate(spark, start: pd.Timestamp, end: pd.Timestamp):
    """Read Cassandra with Spark, filter the two-year window, aggregate to days.

    The point quantity is mean MW, so energy in MWh = MW × period hours.
    MongoDB receives only the selected date, connection, direction and energy.
    """
    from pyspark.sql import functions as F

    raw = spark.read.format("org.apache.spark.sql.cassandra").options(
        keyspace=KEYSPACE, table=TABLE).load()
    selected = (raw.select("connection", "direction", "ts_utc", "quantity_mw", "duration_hours")
                .where((F.col("ts_utc") >= F.lit(start.to_pydatetime().replace(tzinfo=None))) &
                       (F.col("ts_utc") < F.lit(end.to_pydatetime().replace(tzinfo=None)))))
    curated = (selected.withColumn("date_utc", F.to_date("ts_utc"))
               .withColumn("energy_mwh", F.col("quantity_mw") * F.col("duration_hours"))
               .groupBy("connection", "direction", "date_utc")
               .agg(F.sum("energy_mwh").alias("energy_mwh"),
                    F.count("*").alias("period_count"))
               .orderBy("connection", "direction", "date_utc"))
    return curated


def write_to_mongodb(curated, uri: str) -> int:
    """Upsert daily Spark results; verify a read using the same MongoDB client."""
    from pymongo import ASCENDING, MongoClient, UpdateOne

    if not uri:
        raise ValueError("MONGODB_URI is missing.")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, tz_aware=True)
    collection = client[MONGO_DATABASE][MONGO_COLLECTION]
    client.admin.command("ping")
    collection.create_index([
        ("connection", ASCENDING), ("direction", ASCENDING),
        ("date_utc", ASCENDING)], unique=True)
    operations = []
    for row in curated.toLocalIterator():
        date_utc = datetime(row.date_utc.year, row.date_utc.month, row.date_utc.day,
                            tzinfo=timezone.utc)
        key = {"connection": row.connection, "direction": row.direction, "date_utc": date_utc}
        operations.append(UpdateOne(key, {"$set": {
            "energy_mwh": float(row.energy_mwh),
            "period_count": int(row.period_count),
            "source": "ENTSO-E Physical Flows [12.1.G]",
        }}, upsert=True))
        if len(operations) >= 1000:
            collection.bulk_write(operations, ordered=False)
            operations.clear()
    if operations:
        collection.bulk_write(operations, ordered=False)
    count = collection.count_documents({})
    client.close()
    return count


def check_mongodb(uri: str) -> None:
    """Test a real Atlas write/read/delete without touching flow records."""
    from uuid import uuid4
    from pymongo import MongoClient

    if not uri:
        raise ValueError("MONGODB_URI is missing.")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    marker = str(uuid4())
    collection = client[MONGO_DATABASE]["setup_check"]
    inserted = False
    try:
        client.admin.command("ping")
        collection.insert_one({"_id": marker, "purpose": "IND320 connection check"})
        inserted = True
        if collection.find_one({"_id": marker}) is None:
            raise RuntimeError("MongoDB write succeeded but read returned no document.")
    finally:
        if inserted:
            collection.delete_one({"_id": marker})
        client.close()
