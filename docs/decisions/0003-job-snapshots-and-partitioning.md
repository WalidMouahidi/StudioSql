# ADR 0003 — Un snapshot et une table Trino par job

- **Date de constat :** 26 novembre 2026
- **État :** En vigueur
- **Références :** [`ingestion.py`](../../backend/app/services/ingestion.py), [`jobs.py`](../../backend/app/routers/jobs.py), [`models.py`](../../backend/app/models.py)

## Contexte

L'application doit comparer formats, compressions, tailles de lots et partitionnement sans écraser les résultats d'autres extractions. Les tables sources contiennent des colonnes `DATE` et des horodatages.

## Décision matérialisée par l'implémentation

Chaque job lit la table source entière et écrit ses propres objets dans `s3://warehouse/data/<source>/<schema>/<table>/<job_id>/`. Il crée ensuite `lake.billing.job_<job_id>`. Le job accepte Parquet ou CSV, une compression compatible, un lot de 1 à 250 000 lignes et au plus quatre colonnes de partition. Une colonne `DATE` sert directement de clé quotidienne ; pour un horodatage compatible, une clé `<colonne>_day` est dérivée. Sans partition, les fichiers sont au niveau du préfixe du job.

## Conséquences

- Les scénarios de benchmark restent isolés et leur table SQL est identifiable par le résultat du job.
- Chaque nouvel export duplique la table source, consomme de l'espace objet et ajoute une table au catalogue. Le projet ne consolide pas automatiquement les versions d'une même table.
- Le nombre de fichiers peut augmenter avec les partitions et les petits lots. Le tri SQL par colonnes de partition peut rendre l'extraction plus coûteuse.
- Un job échoué peut laisser des objets sans table dans MinIO. Le chargement incrémental et l'évolution du schéma ne sont pas implémentés.

## Options à réévaluer si le contexte change

Table stable mise à jour par incréments, format de table avec transactions (par exemple Iceberg), politique de rétention des snapshots et nettoyage des objets orphelins.
