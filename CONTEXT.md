# Contexte technique — StudioSql

**État vérifié le 26 novembre 2026.** Lire ce fichier en premier pour une tâche sur le projet. Les détails sont dans [l'architecture système](docs/architecture/system.md), [le flux d'extraction](docs/architecture/data-flow.md), [les décisions](docs/decisions/README.md) et [l'évolution](docs/evolution.md).

## Objet

StudioSql est une plateforme locale Docker : elle explore SQL Server, extrait des tables par lots, écrit des fichiers Parquet ou CSV dans MinIO, les enregistre comme tables externes dans le catalogue Hive `lake` de Trino, puis exécute des requêtes SQL et présente des mesures de performance.

```text
SQL Server -> FastAPI / worker -> Parquet ou CSV -> MinIO (S3)
                                            -> catalogue Hive file -> Trino -> SQL
```

Le « catalogue Hive » est le métastore `file` **intégré au connecteur Hive de Trino**. Ses métadonnées sont dans `s3://warehouse/catalog/`. Il n'y a pas de conteneur Hive Metastore distinct.

## Points d'entrée et état persistant

| Élément | Emplacement |
| --- | --- |
| Interface, proxy Nginx, API | `http://localhost:8000/` |
| API directe locale | `http://localhost:8002/` |
| Trino local | `http://localhost:8080/` |
| Console MinIO locale | `http://localhost:9001/` |
| Sources et données SQL Server | volume `sql-data` |
| Objets de données et catalogue Hive | volume MinIO `object-data` |
| Jobs, sources ajoutées, profils et sessions | SQLite `/state/jobs.db` dans `job-data` |
| Résultats de benchmark | `data/results/`, monté dans l'API sur `/results` |

Le compte applicatif est actuellement **un administrateur unique**. Son identifiant et son mot de passe initiaux viennent de `.env` via Compose ; `.env` est ignoré par Git. `GET /health` est public. Les autres routes API, y compris Swagger, demandent le cookie de session ; les écritures demandent aussi `X-StudioSql-CSRF`. Les sessions durent 12 heures et sont révoquées au redémarrage de l'API. Le nom affiché du profil est enregistré dans SQLite ; le mot de passe reste géré dans `.env`.

## Parcours principal

1. `GET /sources` et les routes `/sources/{id}/tables` explorent SQL Server via `pymssql`. Les sources ajoutées par l'UI sont dans `local_sources` (SQLite) ; les sources initiales viennent de `SQL_SOURCES`.
2. `POST /storage/jobs` valide le format, la compression, les colonnes de partition et crée un job `queued` dans SQLite.
3. Un **seul thread worker** dans FastAPI prend les jobs un par un : `queued -> running -> completed` ou `failed`. Il lit avec `fetchmany(batch_size)` ; le lot par défaut est de 50 000 lignes.
4. Chaque job écrit un snapshot sous `s3://warehouse/data/<source>/<schema>/<table>/<job_id>/` et crée une table indépendante `lake.billing.job_<job_id>`. Le partitionnement quotidien est facultatif : `DATE` directement, `DATETIME`/`DATETIME2`/`SMALLDATETIME` via une colonne `<nom>_day`.
5. L'UI interroge Trino via `POST /sql/query`. Les résultats de jobs exposent l'URI MinIO, la table Trino, les volumes et les durées. Le benchmark compare 16 combinaisons CSV/Parquet, partitionnement, compression et tailles de lots.

## Où modifier

| Besoin | Fichiers principaux |
| --- | --- |
| Services, ports, volumes | `docker-compose.yml`, `frontend/nginx.conf` |
| API et cycle des jobs | `backend/app/main.py`, `backend/app/routers/jobs.py`, `backend/app/database.py` |
| Extraction et enregistrement Trino | `backend/app/services/ingestion.py`, `docker/trino/catalog/lake.properties` |
| Sources et jeu fictif | `backend/app/routers/sources.py`, `backend/app/seed_sqlserver.py`, `data/seed.sql` |
| Authentification et profil | `backend/app/auth.py`, `frontend/src/auth.css`, `frontend/src/profile.css` |
| Interface et navigation | `frontend/index.html`, `frontend/src/app.js`, `frontend/src/*.css` |
| Mesures | `backend/app/services/benchmark.py`, `data/results/` |

## Limites actuelles

Snapshots complets uniquement : pas de chargement incrémental, de relance automatique, d'évolution de schéma ni d'Iceberg. Le worker est unique. Le mot de passe applicatif et les identifiants des sources ajoutées ne disposent pas d'un coffre de secrets ; les sources ajoutées sont conservées en JSON dans SQLite. Les ports Trino et MinIO sont des services locaux distincts de l'authentification StudioSql.

## Vérification rapide

```powershell
docker compose config -q
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
node --check frontend/src/app.js
python -m py_compile backend/app/main.py backend/app/auth.py backend/app/services/ingestion.py
```

La configuration initiale est décrite dans [README.md](README.md). Ne jamais afficher ni committer le contenu de `.env` pendant une vérification.
