# ADR 0004 — Compte administrateur unique et session locale

- **Date de constat :** 26 novembre 2026
- **État :** En vigueur
- **Références :** [`auth.py`](../../backend/app/auth.py), [`main.py`](../../backend/app/main.py), [`docker-compose.yml`](../../docker-compose.yml)

## Contexte

L'interface locale et ses routes API doivent demander une connexion avant de donner accès aux sources, aux extractions et aux requêtes SQL.

## Décision matérialisée par l'implémentation

Un seul identifiant administrateur et son mot de passe sont configurés par variables d'environnement. L'API dérive un hash PBKDF2 du mot de passe en mémoire, émet un cookie de session `HttpOnly` et `SameSite=Strict` valable 12 heures, conserve le hash du jeton de session dans SQLite et exige `X-StudioSql-CSRF` pour les écritures. Le nom affiché du profil persiste dans SQLite ; les sessions sont supprimées au redémarrage de l'API. `GET /health` et `POST /auth/login` sont accessibles sans session.

## Conséquences

- L'application est utilisable localement avec un seul compte et une révocation simple par redémarrage.
- Il n'y a ni comptes multiples, ni rôles, ni gestion du mot de passe dans l'interface. La valeur dans `.env` reste la source du mot de passe.
- L'authentification StudioSql ne protège pas les ports locaux de Trino ou de la console MinIO ; leurs propres accès doivent être traités séparément si le déploiement change.
- Les sources ajoutées sont conservées en JSON dans SQLite, y compris leurs identifiants de connexion ; il n'y a pas de coffre de secrets.

## Options à réévaluer si le contexte change

Comptes multiples, fournisseur d'identité, contrôle d'accès aux tables, gestion externalisée des secrets et durcissement des services publiés.
