import sqlite3
from contextlib import closing
from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.config import SOURCES
from app.database import state
from app.models import SourceConfig
from app.services.ingestion import columns, connect_source, sql_connection, tables

router = APIRouter()

def validate_source(source_id):
    if source_id not in SOURCES:
        raise HTTPException(404, "Source inconnue.")


def describe(source_id, schema, table):
    validate_source(source_id)
    try:
        with closing(sql_connection(source_id)) as connection:
            metadata = columns(connection, schema, table)
    except Exception as error:
        raise HTTPException(503, "Connexion ou lecture des métadonnées impossible.") from error
    if not metadata:
        raise HTTPException(404, "Table introuvable.")
    return metadata


@router.get("/sources")
def list_sources():
    return [
        {**{key: source[key] for key in ("id", "host", "database")}, "port": source.get("port", 1433)}
        for source in SOURCES.values()
    ]


@router.get("/sources/{source_id}/test")
def test_source(source_id: str):
    validate_source(source_id)
    return {"source_id": source_id, **check_connection(SOURCES[source_id])}


@router.get("/sources/{source_id}/tables")
def list_tables(source_id: str):
    validate_source(source_id)
    try:
        return tables(source_id)
    except Exception as error:
        raise HTTPException(503, "Lecture des tables impossible.") from error


@router.get("/sources/{source_id}/tables/{table}/columns")
def list_columns(source_id: str, table: str, schema: str = "dbo"):
    return describe(source_id, schema, table)


def check_connection(config):
    start = perf_counter()
    try:
        with closing(connect_source(config)) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT DB_NAME(), CONVERT(varchar(60), SERVERPROPERTY('ProductVersion'))")
            database, version = cursor.fetchone()
    except Exception as error:
        code = error.args[0] if error.args and isinstance(error.args[0], int) else None
        messages = {
            18456: "Le serveur a refusé le nom d’utilisateur ou le mot de passe.",
            4060: "La base demandée est inaccessible. Vérifiez son nom et les droits du compte.",
            20009: "Le serveur SQL Server est inaccessible. Vérifiez l’hôte et le port.",
        }
        raise HTTPException(503, messages.get(code, "Connexion SQL Server impossible.")) from error
    return {"connected": True, "database": database, "version": version,
            "elapsed_ms": round((perf_counter() - start) * 1000)}


@router.post("/sources/test")
def test_draft(config: SourceConfig):
    return check_connection(config.model_dump())


@router.post("/sources", status_code=201)
def add_source(config: SourceConfig):
    with state() as db:
        if config.id in SOURCES:
            raise HTTPException(409, "Cet identifiant existe déjà.")
        try:
            db.execute("INSERT INTO local_sources VALUES (?, ?)", (config.id, config.model_dump_json()))
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "Cet identifiant existe déjà.") from error
    SOURCES[config.id] = config.model_dump()
    return {"id": config.id, "host": config.host, "database": config.database, "port": config.port}
