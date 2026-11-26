import re
from contextlib import closing
from decimal import Decimal
from time import perf_counter

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from trino.dbapi import connect

from app.models import SqlQueryRequest


router = APIRouter()
READ_COMMANDS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "VALUES"}


@router.post("/sql/query")
def execute_read_query(request: SqlQueryRequest):
    statement = request.sql.strip()
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    # A single read query keeps the SQL workspace focused on analysis.
    without_comments = re.sub(r"/\*.*?\*/|--[^\n]*", " ", statement, flags=re.S).strip()
    command = without_comments.split(None, 1)[0].upper() if without_comments else ""
    if ";" in statement or command not in READ_COMMANDS:
        raise HTTPException(422, "Saisissez une seule requête SQL de lecture (SELECT, WITH, SHOW, DESCRIBE ou EXPLAIN).")

    started = perf_counter()
    try:
        with closing(connect(host="trino", port=8080, user="workspace", catalog="lake", schema="billing", request_timeout=60)) as connection:
            with closing(connection.cursor()) as cursor:
                cursor.execute(statement)
                columns = [column[0] for column in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(request.limit + 1) if columns else []
                truncated = len(rows) > request.limit
                rows = rows[:request.limit]
                stats = cursor.stats or {}
    except Exception as error:
        raise HTTPException(400, f"Trino : {error}") from error

    return {
        "columns": columns,
        "rows": jsonable_encoder(rows, custom_encoder={Decimal: str}),
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((perf_counter() - started) * 1000),
        "trino_elapsed_ms": stats.get("elapsedTimeMillis"),
    }
