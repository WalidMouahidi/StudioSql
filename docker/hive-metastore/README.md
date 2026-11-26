# Catalogue Hive

Ce projet utilise le métastore `file` intégré au connecteur Hive de Trino.
Sa configuration se trouve dans `../trino/catalog/lake.properties` et ses métadonnées sont persistées dans MinIO sous `s3://warehouse/catalog/`.
