# ADR 0005 — Deux sources SQL Server et deux workers Trino pour la démo

- **Date de constat :** 28 novembre 2026
- **État :** En vigueur
- **Références :** [`docker-compose.yml`](../../docker-compose.yml), [`coordinator.properties`](../../docker/trino/coordinator.properties), [`worker.properties`](../../docker/trino/worker.properties), [`seed_sqlserver.py`](../../backend/app/seed_sqlserver.py), [guide de démo](../demo-distributed.md)

## Contexte

Le montage initial permettait d'interroger les exports d'une seule source SQL Server avec un seul processus Trino. La démonstration doit montrer à la fois la réunion de données provenant de deux bases indépendantes et l'exécution de tâches SQL sur plusieurs workers Trino.

## Décision matérialisée par l'implémentation

Compose lance un second SQL Server `sqlserver-crm` et expose la source `crm` dans StudioSql. Sa table `CRM.dbo.CustomerProfile` est générée avec les mêmes `customer_id` que les clients de `Billing`, ce qui permet une jointure contrôlable avec `Invoice`. Le service Trino existant devient un coordinateur qui ne traite pas les tâches ; deux conteneurs `trino-worker-1` et `trino-worker-2` utilisent le même catalogue `lake` sur MinIO. La configuration suit les rôles décrits dans la [documentation officielle Trino](https://trino.io/docs/current/installation/deployment.html). L'API attend trois nœuds Trino actifs avant de devenir prête. L'interface peut préparer la jointure entre deux exports Parquet terminés, afficher les nœuds et compter les tâches par worker.

## Conséquences

- Une requête peut lire deux snapshots provenant de serveurs SQL Server différents, puis répartir ses tâches sur deux processus workers Trino.
- Le coordinateur conserve `trino:8080` pour les clients existants. Chaque worker lit les mêmes objets et métadonnées MinIO.
- Le démarrage et la consommation de mémoire augmentent, surtout avec deux instances SQL Server et trois JVM Trino.
- Tous les conteneurs résident sur un seul hôte Docker et MinIO reste mononœud : ce montage montre la distribution **logique** du calcul SQL entre workers, sans stockage distribué ni tolérance aux pannes de plusieurs machines.
- Le worker d'ingestion FastAPI reste unique et séquentiel ; il n'est pas remplacé par les workers Trino.

## Options écartées pour cette démonstration

Une seconde connexion pointant vers le même SQL Server aurait montré une jointure entre exports, mais pas deux serveurs sources indépendants. Un cluster multi-hôtes et un MinIO distribué demanderaient une infrastructure distincte du projet Docker local.
