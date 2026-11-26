import logging
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from app.routers.jobs import job_result
from app.services.ingestion import trino_execute, trino_name

LOG = logging.getLogger("uvicorn.error")
router = APIRouter()

@router.get("/analysis/{job_id}")
def analyze_export(job_id: str, operation: Literal["preview", "count"] = "preview",
                   day: date | None = None, partition: str | None = None):
    result = job_result(job_id)
    name = result["sql_table"]
    if not re.fullmatch(r"lake\.billing\.job_[a-f0-9]{32}", name):
        raise HTTPException(422, "Table SQL invalide.")
    select = "count(*) AS lignes" if operation == "count" else "*"
    statement = f"SELECT {select} FROM {name}"
    if day is not None:
        if partition not in result["partition_by"]:
            raise HTTPException(422, "Sélectionne une colonne de partition.")
        value = f"'{day.isoformat()}'"
        if result["format"] == "parquet":
            value = "DATE " + value
        statement += f" WHERE {trino_name(partition)} = {value}"
    if operation == "preview":
        statement += " LIMIT 100"
    try:
        headers = ["lignes"]
        if operation == "preview":
            description, _ = trino_execute(f"SHOW COLUMNS FROM {name}")
            headers = [row[0] for row in description]
        rows, stats = trino_execute(statement)
    except Exception as error:
        LOG.exception("Lecture Trino impossible")
        raise HTTPException(503, "Trino n’a pas pu lire cet export.") from error
    return {"sql": statement, "columns": headers, "rows": jsonable_encoder(rows, custom_encoder={Decimal: str}), "elapsed_ms": stats.get("elapsedTimeMillis")}
