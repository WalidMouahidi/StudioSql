import json
import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, HTTPException

from app.config import SOURCES
from app.database import state
from app.routers import analysis, jobs, performance, sources, sql
from app.services.ingestion import ingest, initialize

LOG = logging.getLogger("uvicorn.error")

def work(stop, ready):
    while not stop.is_set():
        try:
            initialize()
        except Exception:
            LOG.exception("Services de démarrage indisponibles")
            stop.wait(5)
        else:
            ready.set()
            break

    while not stop.is_set():
        with state() as db:
            job = db.execute("""
                UPDATE jobs SET status = 'running'
                WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY rowid LIMIT 1)
                RETURNING id, request
            """).fetchone()
        if not job:
            stop.wait(0.25)
            continue
        try:
            result = ingest(job["id"], json.loads(job["request"]))
        except Exception as error:
            LOG.exception("Échec du traitement %s", job["id"])
            with state() as db:
                db.execute("UPDATE jobs SET status = 'failed', error = ? WHERE id = ?", (str(error), job["id"]))
        else:
            with state() as db:
                db.execute("UPDATE jobs SET status = 'completed', result = ? WHERE id = ?",
                           (json.dumps(result), job["id"]))


@asynccontextmanager
async def lifespan(app):
    with state() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, request TEXT NOT NULL,
                result TEXT, error TEXT
            )
        """)
        db.execute("UPDATE jobs SET status = 'failed', error = 'Service interrompu' WHERE status = 'running'")
        db.execute("CREATE TABLE IF NOT EXISTS local_sources (id TEXT PRIMARY KEY, config TEXT NOT NULL)")
        for row in db.execute("SELECT config FROM local_sources"):
            config = json.loads(row["config"])
            SOURCES.setdefault(config["id"], config)
    stop, ready = Event(), Event()
    app.state.ready = ready
    worker = Thread(target=work, args=(stop, ready), daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()


app = FastAPI(title="Import SQL Server vers MinIO", lifespan=lifespan)

app.include_router(sources.router)
app.include_router(jobs.router)
app.include_router(analysis.router)
app.include_router(performance.router)
app.include_router(sql.router)


@app.get("/health")
def health():
    if not app.state.ready.is_set():
        raise HTTPException(503, "Initialisation en cours.")
    return {"status": "ready"}
