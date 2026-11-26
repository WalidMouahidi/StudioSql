import argparse
import csv
import json
import os
import random
from itertools import product
from pathlib import Path
from statistics import median
from time import monotonic, perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.ingestion import trino_execute


def api(path, payload=None):
    request = Request(
        "http://api:8000" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"{path} : HTTP {error.code} — {error.read().decode()}") from error


def wait_ready():
    deadline = monotonic() + 300
    while monotonic() < deadline:
        try:
            api("/health")
            return
        except (URLError, RuntimeError):
            sleep(2)
    raise TimeoutError("L'API n'est pas prête.")


def extract(spec):
    identifier = api("/storage/jobs", spec)["id"]
    path = f"/storage/jobs/{identifier}"
    deadline = monotonic() + 1800
    while monotonic() < deadline:
        status = api(path)
        if status["status"] == "failed":
            raise RuntimeError(f"{identifier} : {status['error']}")
        if status["status"] == "completed":
            return api(path + "/result")
        sleep(0.25)
    raise TimeoutError(f"Traitement {identifier} toujours en cours.")


def query(statement, repeats):
    expected, _ = trino_execute(statement)
    times, read_bytes = [], []
    for _ in range(repeats):
        before = perf_counter()
        rows, stats = trino_execute(statement)
        times.append(perf_counter() - before)
        if rows != expected:
            raise RuntimeError(f"Résultat SQL instable : {statement}")
        if stats.get("physicalInputBytes") is not None:
            read_bytes.append(stats["physicalInputBytes"])
    return expected, median(times), median(read_bytes) if read_bytes else None


FIELDS = {
    "format": "Format", "compression": "Compression", "partitioned": "Partition",
    "batch_size": "Lot", "rows": "Lignes", "files": "Fichiers", "bytes": "Octets stockés",
    "extraction_seconds": "Extraction (s)", "load_seconds": "Chargement (s)",
    "scan_seconds": "SQL global (s)", "filter_seconds": "SQL filtré (s)",
}


def report(records, output, repeats):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "benchmark.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    headers = "| " + " | ".join(FIELDS.values()) + " |"
    lines = [
        "# Comparaison sur Invoice", "",
        f"Chaque scénario a été chargé une fois. Les temps SQL sont les médianes de {repeats} "
        "exécutions après une exécution de chauffe.", "",
        headers, "| " + " | ".join("---" for _ in FIELDS) + " |",
    ]
    for row in records:
        cells = [f"{row[key]:.3f}" if isinstance(row[key], float) else str(row[key]) for key in FIELDS]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(["", "## Observations", ""])
    for field, baseline, variant, metric, label, explanation in (
        ("format", "csv", "parquet", "scan_seconds", "Parquet / CSV, lecture globale",
         "Parquet permet de lire la colonne amount seule. Le lecteur CSV doit parcourir les lignes et convertir amount."),
        ("partitioned", "non", "jour", "filter_seconds", "Partitionné / non partitionné, filtre de date",
         "Trino peut écarter les autres jours. L'ouverture de fichiers et le catalogue ont un coût fixe."),
        ("compression", "none", "gzip", "bytes", "Gzip / sans compression, taille stockée",
         "Gzip réduit les octets écrits. Consulter aussi le chargement pour observer le coût de compression."),
        ("batch_size", min(r["batch_size"] for r in records), max(r["batch_size"] for r in records),
         "files", "Grand lot / petit lot, nombre de fichiers",
         "Un grand lot peut réduire le nombre de fichiers. Chaque jour reste un dossier distinct lorsqu'il est partitionné."),
    ):
        match_keys = {"format", "partitioned", "compression", "batch_size"} - {field}
        ratios = [
            b[metric] / a[metric]
            for a in records if a[field] == baseline and a[metric]
            for b in records if b[field] == variant and all(a[key] == b[key] for key in match_keys)
        ]
        if ratios:
            lines.append(f"- **{label}**. Rapport médian de {median(ratios):.2f} sur {len(ratios)} paires. {explanation}")
    (output / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", type=int, nargs=2, default=[5_000, 50_000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("/results"))
    args = parser.parse_args()
    if args.repeats < 1 or len(set(args.batches)) < 2 or any(not 1 <= n <= 250_000 for n in args.batches):
        parser.error("Utiliser deux lots distincts de 1 à 250 000 lignes et au moins une répétition.")

    wait_ready()
    scenarios = list(product(("csv", "parquet"), ("none", "gzip"), (False, True), sorted(args.batches)))
    random.Random(42).shuffle(scenarios)
    records, reference = [], None
    for format_, compression, partitioned, batch in scenarios:
        result = extract(dict(
            source_id="sqlserver", table="Invoice", format=format_, compression=compression,
            partition_by=["invoice_date"] if partitioned else [], batch_size=batch,
        ))
        name = result.pop("sql_table")
        base = f"SELECT count(*), sum(CAST(amount AS DECIMAL(12,2))) FROM {name}"
        date = "'2025-01-15'" if format_ == "csv" else "DATE '2025-01-15'"
        scan, scan_seconds, scan_bytes = query(base, args.repeats)
        filtered, filter_seconds, filter_bytes = query(f"{base} WHERE invoice_date = {date}", args.repeats)
        if scan[0][0] != result["rows"] or (reference is not None and (scan, filtered) != reference):
            raise RuntimeError(f"Résultat SQL incohérent pour {name} : {scan}, {filtered}")
        reference = (scan, filtered)

        records.append(dict(
            **result, sql_table=name, partitioned="jour" if partitioned else "non",
            scan_seconds=scan_seconds, filter_seconds=filter_seconds,
            scan_read_bytes=scan_bytes, filter_read_bytes=filter_bytes,
        ))
        print(f"{len(records)}/16 {format_} {compression} partition={partitioned} lot={batch}", flush=True)

    records.sort(key=lambda row: (row["format"], row["compression"], row["partitioned"], row["batch_size"]))
    report(records, args.output, args.repeats)


if __name__ == "__main__":
    main()
