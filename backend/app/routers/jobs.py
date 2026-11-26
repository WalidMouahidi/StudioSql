import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from app.config import DAY_PARTITION_TYPES
from app.database import state
from app.models import JobRequest
from app.routers.sources import describe

router = APIRouter()

@router.post("/storage/jobs", status_code=202)
def create_job(request: JobRequest, api_request: Request):
    if not api_request.app.state.ready.is_set():
        raise HTTPException(503, "Initialisation en cours.")
    metadata = describe(request.source_id, request.schema_name, request.table)
    compression = request.compression or ("snappy" if request.format == "parquet" else "none")
    if request.format == "csv" and compression not in {"none", "gzip"}:
        raise HTTPException(422, "Le CSV prend en charge none et gzip.")
    by_name = {column["name"]: column["type"] for column in metadata}
    keys = request.partition_by
    normalized_names = {name.lower() for name in by_name}
    partition_names = [
        key.lower() if by_name.get(key) == "date" else f"{key.lower()}_day"
        for key in keys
    ]
    if (
        len(set(key.lower() for key in keys)) != len(keys)
        or (keys and len(keys) >= len(metadata))
        or any(not key.isascii() or not key.isidentifier()
               or by_name.get(key) not in DAY_PARTITION_TYPES for key in keys)
        or len(set(partition_names)) != len(partition_names)
        or any(name in normalized_names for key, name in zip(keys, partition_names)
               if by_name.get(key) != "date")
    ):
        raise HTTPException(422, "Choisissez des colonnes DATE ou DATETIME distinctes ; le nom de la partition journalière doit être libre.")
    identifier = uuid4().hex
    spec = request.model_dump(by_alias=True)
    spec["compression"] = compression
    with state() as db:
        db.execute("INSERT INTO jobs VALUES (?, 'queued', ?, NULL, NULL)", (identifier, json.dumps(spec)))
    return {"id": identifier, "status": "queued"}


def get_job(job_id):
    with state() as db:
        job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise HTTPException(404, "Traitement inconnu.")
    return job


@router.get("/storage/jobs")
def list_jobs():
    with state() as db:
        return [
            {"id": row["id"], "status": row["status"], "request": json.loads(row["request"])}
            for row in db.execute("SELECT id, status, request FROM jobs ORDER BY rowid DESC")
        ]


@router.get("/storage/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    return {"id": job_id, "status": job["status"], "request": json.loads(job["request"]), "error": job["error"]}


@router.get("/storage/jobs/{job_id}/result")
def job_result(job_id: str):
    job = get_job(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, {"status": job["status"], "error": job["error"]})
    return {"id": job_id, "status": job["status"], **json.loads(job["result"])}
