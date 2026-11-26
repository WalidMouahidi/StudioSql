# ADR 0001 — Métastore Hive `file` intégré à Trino

- **Date de constat :** 26 novembre 2026
- **État :** En vigueur
- **Références :** [`lake.properties`](../../docker/trino/catalog/lake.properties), [`ingestion.py`](../../backend/app/services/ingestion.py), [`docker-compose.yml`](../../docker-compose.yml)

## Contexte

Les fichiers Parquet ou CSV déposés dans MinIO doivent être enregistrés dans un catalogue pour être visibles par Trino. Le projet est destiné à une exécution locale simple avec Docker.

## Décision matérialisée par l'implémentation

Le catalogue `lake` utilise le connecteur Hive de Trino avec `hive.metastore=file`. Les métadonnées du catalogue sont persistées dans `s3://warehouse/catalog/` sur MinIO ; les données résident sous `s3://warehouse/data/`. Le service d'ingestion exécute le DDL dans Trino après l'envoi des objets et synchronise les partitions. Aucun conteneur Hive Metastore séparé n'est lancé.

## Conséquences

- Le déploiement local évite un service de catalogue supplémentaire et persiste les métadonnées dans le volume MinIO.
- MinIO et Trino doivent être disponibles pour initialiser et terminer une extraction.
- Une modification manuelle des objets ne suffit pas à créer une table SQL. Le métastore `file` convient à ce montage local ; une exploitation distribuée avec plusieurs writers demanderait une réévaluation du catalogue et de la concurrence.

## Options à réévaluer si le contexte change

Hive Metastore externe, catalogue Iceberg ou service de catalogue géré. Aucune de ces options n'est déployée actuellement.
