# Décisions techniques

Ce registre décrit les choix **déjà présents dans le code**. Il sert à comprendre leurs raisons et leurs limites ; il ne prétend pas que ces choix ont été formellement approuvés lors d'une réunion. Voir [le contexte court](../../CONTEXT.md), [l'architecture](../architecture/system.md) et [le suivi d'évolution](../evolution.md).

| Référence | Décision matérialisée par l'implémentation | État |
| --- | --- | --- |
| [ADR 0001](0001-hive-file-metastore.md) | Catalogue Hive `file` intégré à Trino, sur MinIO | En vigueur |
| [ADR 0002](0002-sqlite-job-worker.md) | Jobs SQLite et worker unique dans FastAPI | En vigueur |
| [ADR 0003](0003-job-snapshots-and-partitioning.md) | Snapshot et table Trino distincts par extraction | En vigueur |
| [ADR 0004](0004-single-admin-auth.md) | Administrateur unique et sessions applicatives | En vigueur |

## Pour une nouvelle décision

Créer `NNNN-sujet.md` et ajouter une ligne ci-dessus. Indiquer : date, état (`Proposée`, `En vigueur` ou `Remplacée`), contexte, décision, conséquences, options écartées et références au code. Une décision qui remplace une autre doit l'indiquer dans les deux fichiers. Mettre à jour les diagrammes et [`CONTEXT.md`](../../CONTEXT.md) si la structure change. Les tâches envisagées, sans décision prise ni code correspondant, vont dans [`docs/evolution.md`](../evolution.md).
