import csv
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/performance/results")
def performance_results():
    path = Path("/results/benchmark.csv")
    if not path.is_file():
        raise HTTPException(404, "Aucune campagne enregistrée.")
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


@router.get("/performance/download/{kind}")
def performance_download(kind: Literal["csv", "md"]):
    path = Path(f"/results/benchmark.{kind}")
    if not path.is_file():
        raise HTTPException(404, "Aucune campagne enregistrée.")
    return FileResponse(path, filename=path.name)
