# Évolution du projet

**Référence au 28 novembre 2026.** Cette page organise l'état du produit et les pistes techniques ; elle ne fixe ni calendrier ni engagement d'implémentation. Les choix déjà matérialisés sont détaillés dans les [décisions](decisions/README.md). Le [contexte court](../CONTEXT.md) résume l'architecture.

## État actuel

| Capacité | État | Point de référence |
| --- | --- | --- |
| Explorer une source SQL Server et ses colonnes | Implémenté | [`sources.py`](../backend/app/routers/sources.py) |
| Extraire par lots vers Parquet ou CSV dans MinIO | Implémenté | [`ingestion.py`](../backend/app/services/ingestion.py) |
| Partitionner par jour sur une colonne choisie | Implémenté | [`jobs.py`](../backend/app/routers/jobs.py), [`ingestion.py`](../backend/app/services/ingestion.py) |
| Créer une table externe Trino par extraction | Implémenté | [`ingestion.py`](../backend/app/services/ingestion.py), [ADR 0001](decisions/0001-hive-file-metastore.md) |
| Suivre les jobs et consulter leur résultat | Implémenté | [`main.py`](../backend/app/main.py), [`jobs.py`](../backend/app/routers/jobs.py) |
| Authentification locale et profil administrateur | Implémenté | [`auth.py`](../backend/app/auth.py), [ADR 0004](decisions/0004-single-admin-auth.md) |
| Comparer 16 scénarios de stockage | Implémenté | [`benchmark.py`](../backend/app/services/benchmark.py), `data/results/` |
| Joindre les exports de deux serveurs SQL Server | Implémenté | [Démo multi-source](demo-distributed.md), [ADR 0005](decisions/0005-cross-source-trino-cluster.md) |
| Répartir les tâches SQL sur deux workers Trino locaux | Implémenté | [`docker-compose.yml`](../docker-compose.yml), [ADR 0005](decisions/0005-cross-source-trino-cluster.md) |

## Pistes à instruire

| Piste | Motivation et décision à prendre | Critère pour la considérer terminée |
| --- | --- | --- |
| Chargement incrémental | Définir une clé de progression fiable, la gestion des modifications/suppressions et la déduplication. Dépend d'un choix de modèle de table. | Une deuxième exécution n'ajoute que les changements attendus et peut être rejouée sans doublon. |
| Relance et nettoyage | Définir l'idempotence d'un job et la durée de conservation des fichiers sans table. | Un job échoué peut être relancé explicitement ; les objets orphelins sont détectés et traités sans toucher aux snapshots valides. |
| Évolution du schéma | Définir les changements admis côté source et leur traduction dans Parquet/Trino. | Ajout, changement compatible et changement incompatible ont chacun un comportement documenté et vérifié. |
| Apache Iceberg | Évaluer un catalogue Iceberg, les transactions et le remplacement éventuel du métastore Hive `file`. | Un scénario bout en bout crée, met à jour et interroge une table Iceberg ; le benchmark la compare aux snapshots Hive existants. |
| Concurrence de l'ingestion | Décider si plusieurs workers **d'ingestion FastAPI** ou instances API sont nécessaires. | Aucun job n'est exécuté deux fois sous concurrence ; l'état reste cohérent après arrêt brutal. |
| Distribution multi-hôtes du stockage et du calcul | Étudier MinIO distribué ou S3 externe, placement des nœuds Trino et tolérance aux pannes. | Perte d'un hôte supportée selon un scénario documenté ; les données restent disponibles. |
| Sécurité des sources et multiutilisateur | Définir un coffre de secrets, des rôles et les limites de l'accès SQL direct à Trino/MinIO. | Les identifiants des sources ne sont plus stockés en clair dans SQLite ; les droits sont testés de bout en bout. |
| Observabilité et vérifications automatiques | Ajouter des mesures fiables du pipeline et des tests aux frontières SQL Server, MinIO et Trino. | Les échecs sont identifiables par job ; les contrats d'extraction et de catalogue sont vérifiés automatiquement. |

## Règle de mise à jour

Quand une piste est décidée, créer ou mettre à jour une ADR avec les alternatives et les conséquences. Quand elle est implémentée, déplacer sa ligne dans **État actuel**, mettre à jour les diagrammes d'[architecture](architecture/system.md) et de [flux](architecture/data-flow.md), puis corriger [`CONTEXT.md`](../CONTEXT.md). Ne dater « implémenté » qu'après vérification du code et du comportement concerné.
