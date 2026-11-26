import csv
import gzip
import io
from datetime import datetime
from collections import defaultdict
from contextlib import closing
from time import perf_counter
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq
import pymssql
from minio import Minio
from trino.dbapi import connect as trino_connect

from app.config import BUCKET, SOURCES
from app.seed_sqlserver import seed_demo

OBJECTS = Minio("minio:9000", access_key="localadmin", secret_key="localminio2026", secure=False)


def sql_connection(source_id, database=None):
    return connect_source(SOURCES[source_id], database)


def connect_source(source, database=None):
    return pymssql.connect(
        server=source["host"], port=str(source.get("port", 1433)),
        user=source["user"], password=source["password"],
        database=database or source["database"], login_timeout=source.get("login_timeout", 5),
        timeout=300, tds_version="7.4", encryption=source.get("encryption"),
    )


def initialize():
    seed_demo(sql_connection)
    if not OBJECTS.bucket_exists(BUCKET):
        OBJECTS.make_bucket(BUCKET)
    trino_execute("CREATE SCHEMA IF NOT EXISTS lake.billing")


def tables(source_id):
    with closing(sql_connection(source_id)) as connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT s.name, t.name FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            ORDER BY s.name, t.name
        """)
        return [{"schema": schema, "table": table} for schema, table in cursor]


def columns(connection, schema, table):
    cursor = connection.cursor(as_dict=True)
    cursor.execute("""
        SELECT c.name, TYPE_NAME(c.system_type_id) AS type, c.precision,
               c.scale, c.max_length, c.is_nullable
        FROM sys.columns c
        JOIN sys.tables t ON c.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = %s AND t.name = %s AND c.is_hidden = 0
        ORDER BY c.column_id
    """, (schema, table))
    return cursor.fetchall()


TEXT = {"varchar", "nvarchar", "char", "nchar", "text", "ntext", "xml", "uniqueidentifier"}
BINARY = {"binary", "varbinary", "image", "timestamp"}


def column_types(column):
    kind = column["type"]
    if kind in TEXT:
        return pa.string(), "VARCHAR"
    if kind in BINARY:
        return pa.binary(), "VARBINARY"
    if kind in {"decimal", "numeric", "money", "smallmoney"}:
        precision, scale = column["precision"], column["scale"]
        return pa.decimal128(precision, scale), f"DECIMAL({precision},{scale})"
    if kind in {"datetime", "datetime2", "smalldatetime"}:
        return pa.timestamp("us"), "TIMESTAMP(6)"
    types = {
        "bit": (pa.bool_(), "BOOLEAN"),
        "tinyint": (pa.int16(), "SMALLINT"),
        "smallint": (pa.int16(), "SMALLINT"),
        "int": (pa.int32(), "INTEGER"),
        "bigint": (pa.int64(), "BIGINT"),
        "real": (pa.float32(), "REAL"),
        "float": (pa.float64(), "DOUBLE"),
        "date": (pa.date32(), "DATE"),
    }
    if kind not in types:
        raise ValueError(f"Type SQL Server non pris en charge : {kind} ({column['name']}).")
    return types[kind]


def sqlserver_name(value):
    return "[" + value.replace("]", "]]") + "]"


def trino_name(value):
    return '"' + value.replace('"', '""') + '"'


def trino_execute(statement):
    with closing(trino_connect(host="trino", port=8080, user="ingestion", request_timeout=60)) as connection:
        with closing(connection.cursor()) as cursor:
            cursor.execute(statement)
            rows = cursor.fetchall()
            return rows, cursor.stats


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    result = str(value)
    if "\n" in result or "\r" in result:
        raise ValueError("Le lecteur CSV Hive ne prend pas en charge les champs multilignes.")
    return result


def encode(rows, indexes, arrow_fields, job):
    if job["format"] == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL, doublequote=False, escapechar="\\", lineterminator="\n")
        writer.writerows([csv_value(row[index]) for index in indexes] for row in rows)
        data = output.getvalue().encode("utf-8")
        return gzip.compress(data, mtime=0) if job["compression"] == "gzip" else data

    arrays = []
    for index, field in zip(indexes, arrow_fields):
        values = [row[index] for row in rows]
        if pa.types.is_string(field.type):
            values = [str(value) if value is not None else None for value in values]
        arrays.append(pa.array(values, type=field.type))
    output = io.BytesIO()
    pq.write_table(
        pa.Table.from_arrays(arrays, schema=pa.schema(arrow_fields)),
        output, compression=None if job["compression"] == "none" else job["compression"],
    )
    return output.getvalue()


def ingest(job_id, job):
    source_id, schema, table = job["source_id"], job["schema"], job["table"]
    path = "/".join(quote(part, safe="") for part in (source_id, schema, table))
    prefix = f"data/{path}/{job_id}/"
    location = f"s3://{BUCKET}/{prefix}"
    destination = f"lake.billing.job_{job_id}"
    metrics = dict(rows=0, files=0, bytes=0, extraction_seconds=0.0,
                   serialization_seconds=0.0, upload_seconds=0.0)
    started = perf_counter()

    with closing(sql_connection(source_id)) as connection:
        metadata = columns(connection, schema, table)
        names = [column["name"] for column in metadata]
        partitions = job["partition_by"]
        partition_indexes = [names.index(key) for key in partitions]
        partition_names = [
            name.lower() if metadata[index]["type"] == "date" else f"{name.lower()}_day"
            for name, index in zip(partitions, partition_indexes)
        ]
        data_indexes = [
            i for i in range(len(names))
            if i not in partition_indexes or metadata[i]["type"] != "date"
        ]
        types = [column_types(column) for column in metadata]
        fields = [pa.field(names[i].lower(), types[i][0]) for i in data_indexes]
        select = ", ".join(map(sqlserver_name, names))
        table_name = f"{sqlserver_name(schema)}.{sqlserver_name(table)}"
        query = f"SELECT {select} FROM {table_name}"
        if partitions:
            query += " ORDER BY " + ", ".join(map(sqlserver_name, partitions))
        cursor = connection.cursor()
        before = perf_counter()
        cursor.execute(query)
        metrics["extraction_seconds"] += perf_counter() - before

        while True:
            before = perf_counter()
            batch = cursor.fetchmany(job["batch_size"])
            metrics["extraction_seconds"] += perf_counter() - before
            if not batch:
                break

            before = perf_counter()
            groups = defaultdict(list)
            for row in batch:
                key = tuple(row[i].date() if isinstance(row[i], datetime) else row[i]
                            for i in partition_indexes)
                groups[key].append(row)
            metrics["serialization_seconds"] += perf_counter() - before
            for key, rows in groups.items():
                folder = "".join(
                    f"{name}={value if value is not None else '__HIVE_DEFAULT_PARTITION__'}/"
                    for name, value in zip(partition_names, key)
                )
                suffix = job["format"] + (".gz" if job["format"] == "csv" and job["compression"] == "gzip" else "")
                object_key = f"{prefix}{folder}part-{metrics['files']:08d}.{suffix}"
                before = perf_counter()
                data = encode(rows, data_indexes, fields, job)
                metrics["serialization_seconds"] += perf_counter() - before
                before = perf_counter()
                OBJECTS.put_object(BUCKET, object_key, io.BytesIO(data), len(data))
                metrics["upload_seconds"] += perf_counter() - before
                metrics["rows"] += len(rows)
                metrics["files"] += 1
                metrics["bytes"] += len(data)

    definitions = [
        f"{trino_name(names[i])} {'VARCHAR' if job['format'] == 'csv' else types[i][1]}"
        for i in data_indexes
    ]
    definitions.extend(
        f"{trino_name(name)} {'VARCHAR' if job['format'] == 'csv' else 'DATE'}"
        for name in partition_names
    )
    properties = [f"format = '{job['format'].upper()}'", f"external_location = '{location}'"]
    if partition_names:
        properties.append("partitioned_by = ARRAY[" + ", ".join(f"'{key}'" for key in partition_names) + "]")
    before = perf_counter()
    try:
        trino_execute(f"CREATE TABLE {destination} ({', '.join(definitions)}) WITH ({', '.join(properties)})")
        if partitions and metrics["files"]:
            trino_execute(f"CALL lake.system.sync_partition_metadata('billing', 'job_{job_id}', 'ADD')")
    except Exception:
        trino_execute(f"DROP TABLE IF EXISTS {destination}")
        raise
    metrics["catalog_seconds"] = perf_counter() - before
    metrics["load_seconds"] = metrics["serialization_seconds"] + metrics["upload_seconds"] + metrics["catalog_seconds"]
    return dict(
        **metrics, storage_uri=location, sql_table=destination,
        format=job["format"], compression=job["compression"], partition_by=partition_names,
        partition_source_columns=partitions,
        batch_size=job["batch_size"], total_seconds=perf_counter() - started,
    )
