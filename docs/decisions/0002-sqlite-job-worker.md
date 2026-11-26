# ADR 0002 — État des jobs dans SQLite, worker unique dans l'API

- **Date de constat :** 26 novembre 2026
- **État :** En vigueur
- **Références :** [`main.py`](../../backend/app/main.py), [`database.py`](../../backend/app/database.py), [`jobs.py`](../../backend/app/routers/jobs.py), [`docker-compose.yml`](../../docker-compose.yml)

## Contexte

Une extraction longue doit répondre immédiatement à l'appel API, publier un état consultable et conserver son historique après le redémarrage du conteneur.

## Décision matérialisée par l'implémentation

`POST /storage/jobs` écrit un job `queued` dans SQLite (`/state/jobs.db`, volume `job-data`) et renvoie HTTP 202. Un thread du processus FastAPI prend les jobs dans l'ordre d'insertion, un par un, et les fait passer à `running`, puis `completed` ou `failed`. Au redémarrage, un job resté `running` devient `failed` ; les jobs `queued` restent en attente.

## Conséquences

- L'historique survit au redémarrage du conteneur et la mémoire n'est pas utilisée comme file de jobs.
- Le débit est limité par un seul worker. Déployer plusieurs processus API avec le même cycle de vie du worker n'est pas un mode de fonctionnement validé : chaque processus lancerait son propre thread.
- Il n'y a ni relance automatique, ni reprise d'une extraction au milieu d'un lot, ni nettoyage garanti des objets d'un job échoué.

## Options à réévaluer si le contexte change

Worker séparé, file de messages et stockage transactionnel partagé si la concurrence, la reprise fine ou plusieurs instances deviennent nécessaires.
