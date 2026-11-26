import os
from contextlib import closing
from pathlib import Path

from app.config import SEED_SQL_PATH


def seed_demo(sql_connection):
    if os.getenv("SEED_DEMO", "1") != "1":
        return
    total = int(os.getenv("DEMO_INVOICES", "1000000"))
    if not 1 <= total <= 1_000_000:
        raise ValueError("DEMO_INVOICES doit être compris entre 1 et 1 000 000.")
    with closing(sql_connection("sqlserver", "master")) as connection:
        connection.autocommit(True)
        connection.cursor().execute("IF DB_ID('Billing') IS NULL EXEC('CREATE DATABASE Billing')")
    with closing(sql_connection("sqlserver")) as connection:
        connection.cursor().execute(Path(SEED_SQL_PATH).read_text(encoding="utf-8"), (total,))
        connection.commit()
