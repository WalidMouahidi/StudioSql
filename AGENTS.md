# Repères pour les prochains travaux

1. Lire d'abord [CONTEXT.md](CONTEXT.md). Il donne l'état technique courant et les chemins utiles sans parcourir tout le dépôt.
2. Ouvrir ensuite uniquement la vue d'architecture, la décision ou le module concerné par la tâche : [architecture](docs/architecture/system.md), [flux de données](docs/architecture/data-flow.md), [décisions](docs/decisions/README.md), [évolution](docs/evolution.md).
3. Le code et `docker-compose.yml` restent la source de vérité. Si un document ne correspond plus au code, corriger le document dans le même changement.
4. Enregistrer toute décision qui modifie les frontières des services, le stockage, le catalogue, les API ou l'authentification dans `docs/decisions/`. Mettre à jour `docs/evolution.md` quand une capacité change d'état.
5. Ne jamais versionner `.env`, les mots de passe, les jetons de session ou les données des volumes Docker. Les exemples publics vont dans `.env.example`.

Les pistes d'évolution documentées ne constituent pas une demande de les implémenter. Les instructions de l'utilisateur pour la tâche en cours priment.
