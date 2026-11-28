# Architecture système

**État : 28 novembre 2026.** Cette vue décrit l'implémentation actuelle. Voir aussi [le flux d'extraction](data-flow.md), la [démo multi-source](../demo-distributed.md) et le [contexte court](../../CONTEXT.md).

## Chaîne analytique

```mermaid
flowchart LR
    SQL[(SQL Server<br/>Billing)] -->|pymssql, lots| ING[FastAPI<br/>service d'ingestion]
    CRM[(SQL Server<br/>CRM)] -->|pymssql, lots| ING
    ING -->|Parquet ou CSV| OBJ[(MinIO<br/>s3://warehouse/data/)]
    ING -->|DDL et synchronisation| TRINO[Trino<br/>coordinateur]
    TRINO --> W1[Worker 1]
    TRINO --> W2[Worker 2]
    OBJ -->|fichiers de données| W1
    OBJ -->|fichiers de données| W2
    TRINO <--> CAT[(Métastore Hive file<br/>s3://warehouse/catalog/)]
    TRINO -->|résultats SQL| API[API StudioSql]
    API --> WEB[Interface web]
```

Le catalogue est une **fonction du connecteur Hive de Trino** configurée dans [`docker/trino/catalog/lake.properties`](../../docker/trino/catalog/lake.properties). Trino persiste ses métadonnées dans MinIO. Le dossier `docker/hive-metastore/` documente ce choix ; aucun service Hive Metastore n'est lancé par Compose. Le dépôt d'objets seul ne rend pas une table interrogeable : le **worker d'ingestion** crée une table externe, puis synchronise ses partitions éventuelles. Le coordinateur Trino planifie les requêtes ; deux workers Trino exécutent les tâches.

## Déploiement local

```mermaid
flowchart TB
    B[Navigateur] -->|localhost:8000| N[Nginx<br/>SPA Vite et proxy]
    N -->|HTTP /auth, /sources, /storage, /sql...| A[FastAPI<br/>API et worker unique]
    A -->|pymssql| S[(SQL Server<br/>volume sql-data)]
    A -->|pymssql| C[(SQL Server CRM<br/>volume crm-data)]
    A -->|S3 API| M[(MinIO<br/>volume object-data)]
    A -->|DDL et requêtes| T[Trino coordinateur<br/>lake.billing]
    T -->|tâches SQL| W1[Trino worker 1]
    T -->|tâches SQL| W2[Trino worker 2]
    T -->|catalogue| M
    W1 -->|fichiers| M
    W2 -->|fichiers| M
    A -->|jobs, sources, profils, sessions| D[(SQLite<br/>volume job-data)]
    A -->|lecture des rapports| R[data/results<br/>montage local]
```

| Service Compose | Responsabilité | Accès depuis l'hôte |
| --- | --- | --- |
| `frontend` | Nginx sert le bundle Vite et relaie l'API | `127.0.0.1:8000` |
| `api` | FastAPI, authentification, exploration, extraction, SQL, benchmark | `127.0.0.1:8002` |
| `sqlserver` | Base source `Billing`, tables `dbo.Customer`, `dbo.Invoice`, `dbo.Payment` | aucun port publié |
| `sqlserver-crm` | Base source indépendante `CRM`, table `dbo.CustomerProfile` ; identifiants clients compatibles avec Billing | aucun port publié |
| `minio` | Objets S3 compatibles, données et métadonnées | console `127.0.0.1:9001` |
| `trino` | Coordinateur, catalogue `lake`, schéma `billing`, planification SQL | `127.0.0.1:8080` |
| `trino-worker-1`, `trino-worker-2` | Exécution des tâches SQL, lecture des objets MinIO | aucun port publié |

Le code d'API est dans [`backend/app/`](../../backend/app/), les routes dans [`backend/app/routers/`](../../backend/app/routers/) et le flux de traitement dans [`backend/app/services/ingestion.py`](../../backend/app/services/ingestion.py). L'interface est une SPA HTML/CSS/JavaScript dans [`frontend/`](../../frontend/) ; la navigation utilise des fragments d'URL (`#sources`, `#workspace`, `#jobs`, `#sql`, `#history`, `#profile`). En développement Vite, [`frontend/vite.config.ts`](../../frontend/vite.config.ts) relaie également les routes API vers `localhost:8002`.

## Frontières de persistance et de sécurité

- `sql-data` et `crm-data` conservent les deux bases sources fictives ; `object-data` conserve les exports et le catalogue ; `job-data` conserve `jobs.db`. `data/results/` est un montage du dépôt, pas un volume Docker nommé.
- Le navigateur ne se connecte pas directement à SQL Server ni à MinIO pour les extractions. FastAPI orchestre ces accès. Le navigateur utilise l'API via Nginx et reçoit des résultats SQL limités.
- L'authentification StudioSql protège l'API, y compris `/docs` et `/openapi.json`. Seul `GET /health` reste public. Les fichiers statiques de l'interface sont publics mais ne contiennent pas les données SQL.
- Le cookie de session est `HttpOnly`, `SameSite=Strict`, valable 12 heures. Les requêtes d'écriture exigent le jeton CSRF de la session. Les sessions sont effacées au redémarrage de l'API ; le profil affiché persiste.
- Trino et la console MinIO sont publiés uniquement sur la boucle locale et ne partagent pas l'authentification de l'API. Les identifiants de démonstration des services sont définis dans Compose et dans le catalogue Trino : ce montage est destiné au poste local.
- Les deux workers Trino et le coordinateur sont trois processus Docker sur le même ordinateur. MinIO reste mononœud. La démonstration répartit le calcul SQL entre workers, sans distribution physique du stockage ni tolérance aux pannes entre machines.

## Reprise après incident

Au démarrage, un job resté `running` est marqué `failed` avec l'erreur « Service interrompu ». Les jobs `queued` restent en base et le worker les reprend. En cas d'échec pendant l'enregistrement dans Trino, la table externe partiellement créée est supprimée ; les objets déjà envoyés à MinIO peuvent néanmoins rester. Une relance automatique et un nettoyage des objets orphelins ne sont pas implémentés.
