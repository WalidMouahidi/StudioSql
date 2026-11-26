# Analyse des factures avec SQL Server, MinIO et Trino

Le service FastAPI découvre les tables SQL Server et extrait une table à la fois avec un curseur par lots. Il écrit des objets Parquet ou CSV dans MinIO puis crée une table externe dans le catalogue Hive `lake` de Trino. Le métastore Hive sur fichiers est persisté dans MinIO sous `s3://warehouse/catalog/`. Les jobs et leurs résultats sont persistés dans SQLite.

## Références pour comprendre et faire évoluer le projet

Commencer par le [contexte technique court](CONTEXT.md) avant de parcourir le code. Les vues d'[architecture système](docs/architecture/system.md) et de [flux de données](docs/architecture/data-flow.md) décrivent les composants et le parcours d'un job. Le [registre des décisions](docs/decisions/README.md) explique les choix techniques en vigueur ; le [suivi d'évolution](docs/evolution.md) sépare les capacités implémentées des pistes à étudier. Les [consignes du dépôt](AGENTS.md) indiquent comment maintenir ces références à jour.

## Structure

```text
projet-un/
├── backend/
│   ├── app/
│   │   ├── routers/         # Sources, jobs, analyse et performances
│   │   ├── services/        # Ingestion et benchmark
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── seed_sqlserver.py
│   ├── Dockerfile
│   └── requirements.txt
├── data/
│   ├── seed.sql         # Génération des données Billing
│   └── results/         # Rapports de performance
├── docker/
│   ├── hive-metastore/ # Documentation du catalogue Hive sur fichiers
│   ├── minio/
│   └── trino/catalog/
├── frontend/
│   ├── src/             # Interface du wireframe
│   ├── Dockerfile
│   ├── index.html
│   ├── nginx.conf
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── .env.example
├── .env                 # Identifiants locaux, non versionnés
└── docker-compose.yml
```

## Démarrer

Docker Desktop doit utiliser des conteneurs Linux. SQL Server Developer cible Linux x86-64. Le premier démarrage télécharge les images et compile MinIO à partir de la version communautaire amont `RELEASE.2025-10-15T17-29-55Z`. Les accès publiés sont limités à la boucle locale.

Copier `.env.example` vers `.env`, puis définir `STUDIOSQL_ADMIN_PASSWORD` avec un mot de passe de 12 caractères minimum. Le compte par défaut est `admin`. Le fichier `.env` reste local et n'est pas publié dans Git.

Pour copier uniquement le mot de passe dans le presse-papiers depuis la racine du projet (PowerShell), exécuter la commande suivante, puis le coller dans le formulaire de connexion. Ne pas copier le préfixe `STUDIOSQL_ADMIN_PASSWORD=`.

```powershell
((Get-Content .env | Select-String '^STUDIOSQL_ADMIN_PASSWORD=').Line -replace '^STUDIOSQL_ADMIN_PASSWORD=', '') | Set-Clipboard
```

```powershell
docker compose up --build -d
docker compose logs -f api
```

L'API est prête quand `GET http://localhost:8000/health` renvoie `200`. Ouvrir `http://localhost:8000/` pour se connecter. Les routes de l'API et Swagger (`http://localhost:8000/docs`) demandent une session. La console MinIO est sur `http://localhost:9001` (utilisateur `localadmin`, mot de passe `localminio2026`). Trino écoute sur `http://localhost:8080`.

La connexion crée une session de 12 heures dans un cookie `HttpOnly` et `SameSite=Strict`. Le bouton **Se déconnecter** révoque la session. Une modification de `STUDIOSQL_ADMIN_PASSWORD` suivie d'un redémarrage de l'API révoque aussi les sessions existantes. Pour utiliser l'API directement, appeler `POST /auth/login`, conserver le cookie reçu et transmettre le `csrf_token` retourné dans l'en-tête `X-StudioSql-CSRF` pour les requêtes d'écriture.

Au premier démarrage, le script crée la base `Billing` avec 1 000 000 de factures, 100 000 clients et 750 000 paiements fictifs. Pour un premier essai plus court, définir `DEMO_INVOICES=50000` dans `.env` avant de démarrer sur un volume SQL neuf. Le volume existant conserve ses données.

Pour ajouter des sources, définir `SQL_SOURCES` dans `.env` comme tableau JSON. Exemple de configuration d'une source externe accessible depuis les conteneurs Docker Desktop :

```dotenv
SEED_DEMO=0
SQL_SOURCES='[{"id":"compta","host":"host.docker.internal","port":1433,"database":"Billing","user":"reader","password":"mot-de-passe"}]'
```

Chaque entrée comporte un identifiant unique. Le compte de lecture SQL doit avoir accès aux tables à explorer et à extraire. Les identifiants locaux fournis par Compose servent à la démonstration.

## Explorer et extraire une table

| Méthode | Route | Résultat |
| --- | --- | --- |
| GET | `/sources` | Sources configurées |
| GET | `/sources/sqlserver/test` | Test de connexion |
| GET | `/sources/sqlserver/tables` | Liste des tables avec leur schéma |
| GET | `/sources/sqlserver/tables/Invoice/columns?schema=dbo` | Colonnes, types, précision et nullabilité |
| POST | `/storage/jobs` | Planifie une extraction, réponse HTTP 202 |
| GET | `/storage/jobs/{id}` | `queued`, `running`, `completed` ou `failed` |
| GET | `/storage/jobs/{id}/result` | Emplacement MinIO, table Trino, lignes, fichiers, octets et durées |

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$secret = Read-Host "Mot de passe StudioSql" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential("admin", $secret)
$loginBody = @{ username = $credential.UserName; password = $credential.GetNetworkCredential().Password } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -ContentType application/json -Body $loginBody -WebSession $session
$headers = @{ 'X-StudioSql-CSRF' = $login.csrf_token }
$job = Invoke-RestMethod -Method Post -Uri http://localhost:8000/storage/jobs -ContentType application/json -Headers $headers -WebSession $session -Body '{"source_id":"sqlserver","table":"Invoice","format":"parquet","partition_by":["invoice_date"]}'
Invoke-RestMethod "http://localhost:8000/storage/jobs/$($job.id)" -WebSession $session
$result = Invoke-RestMethod "http://localhost:8000/storage/jobs/$($job.id)/result" -WebSession $session
$result
docker compose exec -T trino trino --execute "SELECT invoice_date, count(*) AS invoices, sum(amount) AS total FROM $($result.sql_table) WHERE invoice_date = DATE '2025-01-15' GROUP BY invoice_date"
```

Appeler la route du résultat après le passage à `completed`. Le schéma source par défaut est `dbo`. Le lot par défaut est de 50 000 lignes. Parquet accepte `snappy` (défaut), `none`, `gzip` et `zstd`. CSV accepte `none` (défaut) et `gzip`.

Un export crée un préfixe `data/<source>/<schéma>/<table>/<job>/` et une table indépendante. Dans **Studio → Extraction**, la liste des colonnes de partition est chargée depuis la table sélectionnée. Une colonne `DATE` forme directement une partition quotidienne, par exemple `invoice_date=2025-01-15/`. Une colonne `DATETIME`, `DATETIME2` ou `SMALLDATETIME` forme une colonne de partition dérivée, par exemple `created_at_day=2025-01-15/` ; l'horodatage `created_at` reste dans les données. Les noms de partition sont normalisés en minuscules dans Hive. Le service synchronise ces partitions avec le métastore avant de signaler la fin du job. Une forte cardinalité augmente le nombre de fichiers et le coût de leur ouverture.

Parquet conserve les types et les valeurs nulles. La précision des horodatages est à la microseconde. Le format CSV expose chaque colonne en `VARCHAR` dans Trino, représente les valeurs nulles par un champ vide et refuse les champs multilignes. Trino peut convertir les colonnes CSV avec `CAST` pour les analyses.

## Comparer les performances

La campagne sur un million de factures est disponible dans le [rapport mesuré](data/results/benchmark.md) et le [CSV détaillé](data/results/benchmark.csv). Pour la reproduire avec les données de démonstration chargées, lancer :

```powershell
docker compose exec -T api python -m app.services.benchmark
```

Le script combine les deux formats, les deux modes de partitionnement, Gzip ou aucune compression, et des lots de 5 000 ou 50 000 lignes. Il produit `data/results/benchmark.csv` et `data/results/benchmark.md` avec 16 lignes, les mesures dans un tableau et les comparaisons par paires. Les options `--batches 1000 10000` et `--repeats 1` permettent un essai plus court.

- **Taille**. Somme des octets des objets de données uploadés.
- **Extraction**. Temps cumulé de soumission du SELECT et de lecture des lots. Le tri SQL des exports partitionnés est inclus.
- **Chargement**. Temps cumulé de regroupement, sérialisation, transfert MinIO et enregistrement des métadonnées Trino.
- **SQL**. Temps client médian sur trois exécutions après une chauffe pour un agrégat global et le même agrégat sur une journée. Le script compare aussi les résultats des agrégats entre scénarios. Le CSV donne les octets lus si Trino publie cette statistique.

Parquet peut lire uniquement la colonne nécessaire à l'agrégat global, alors que CSV doit décoder les lignes. Sur la requête filtrée, le partitionnement permet d'écarter les jours hors filtre, avec un coût de métadonnées qui augmente avec le nombre de dossiers. La compression échange du temps CPU contre un volume de stockage et des transferts plus faibles. La taille du lot agit sur la mémoire du service et sur le nombre de fichiers. Les chiffres mesurent la configuration locale, les données de démonstration et des lectures après chauffe.

`docker compose down` arrête les services et conserve les volumes.

## Interface web

Ouvrir [StudioSql](http://localhost:8000/) après `docker compose up --build -d`.
La plateforme locale partage l’API et les volumes du projet.

- **Data Sources**. Rechercher les sources, consulter leur dernier test dans le navigateur et tester une connexion SQL Server avant de l’enregistrer.
- **Studio**. L'arborescence à gauche liste les tables SQL Server. Les onglets **Structure**, **Extraction**, **Éditeur SQL** et **Historique** donnent accès à la table sélectionnée, aux exports, aux requêtes et aux jobs enregistrés. L'onglet **Historique** affiche l'état de chaque job, son emplacement MinIO et sa table Trino.
- **Profil**. Ouvrir l'avatar en haut à droite pour voir son compte, modifier le nom affiché, consulter les sessions et déconnecter les autres navigateurs. Le mot de passe administrateur reste configuré dans `.env`.
- **Éditeur SQL**. Sélectionner un export pour préparer une requête, utiliser **Aperçu** ou **Compter**, ou écrire une requête de lecture personnalisée. **Ctrl+Entrée** exécute la requête ; le tableau affiche au plus 200 lignes dans l'interface. L'API `POST /sql/query` accepte jusqu'à 1 000 lignes avec le paramètre `limit`.
- **Performances**. Filtrer les scénarios mesurés et télécharger les données ou le rapport.

Les sources ajoutées par l’interface sont enregistrées dans le volume SQLite local avec leurs paramètres de connexion. Swagger reste accessible sur [la documentation API](http://localhost:8000/docs).
