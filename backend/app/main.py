import json
import logging
import secrets
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Request

from app import auth
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
    auth.initialize_auth()
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


app = FastAPI(title="StudioSql API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(sources.router)
app.include_router(jobs.router)
app.include_router(analysis.router)
app.include_router(performance.router)
app.include_router(sql.router)


@app.middleware("http")
async def require_session(request: Request, call_next):
    if request.method == "GET" and request.url.path == "/health":
        return await call_next(request)
    if request.method == "POST" and request.url.path == "/auth/login":
        return await call_next(request)

    session = auth.session_for(request)
    if session is None:
        return auth.json_error(401, "Authentification requise.")
    request.state.username = session["username"]
    request.state.csrf_token = session["csrf_token"]
    request.state.expires_at = session["expires_at"]
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        submitted = request.headers.get("x-studiosql-csrf", "")
        if not secrets.compare_digest(submitted, session["csrf_token"]):
            return auth.json_error(403, "Jeton de session manquant ou invalide.")
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    if not app.state.ready.is_set():
        raise HTTPException(503, "Initialisation en cours.")
    return {"status": "ready"}
