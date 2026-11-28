# Démonstration multi-source et calcul SQL réparti

**État vérifié le 28 novembre 2026.** Cette démo utilise deux SQL Server indépendants et un Trino local à un coordinateur et deux workers. Elle montre la répartition de tâches entre processus Docker sur **un seul PC**. MinIO reste un stockage objet mononœud.

## Démarrer et vérifier les services

```powershell
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
docker compose exec -T trino trino --execute "SELECT node_id, coordinator, state FROM system.runtime.nodes ORDER BY coordinator DESC, node_id"
```

Attendre `{"status":"ready"}`. Le démarrage des trois nœuds Trino et du nouveau SQL Server peut prendre plusieurs minutes sur Docker Desktop. La requête des nœuds doit renvoyer **une ligne `coordinator=true` et deux lignes `coordinator=false`**, toutes `active`. Le service `trino` garde le port hôte 8080 ; les workers n'exposent pas de port hôte.

La configuration Compose fournit par défaut deux sources : `sqlserver` sur `Billing` et `crm` sur `CRM`. Si `.env` définit `SQL_SOURCES`, cette valeur remplace la liste par défaut : il faut y inclure les deux sources. `SEED_DEMO=1` prépare `dbo.CustomerProfile` dans CRM avec les mêmes `customer_id` que Billing. Une installation neuve avec `DEMO_INVOICES=1000000` contient 1 000 000 factures et 100 000 profils CRM.

## Parcours dans StudioSql

1. Ouvrir `http://localhost:8000/` et se connecter. Dans **Data Sources**, tester `sqlserver` et `crm`. Dans **Studio**, chaque source doit montrer sa propre arborescence : `dbo.Invoice` côté Billing et `dbo.CustomerProfile` côté CRM.
2. Extraire `sqlserver / dbo.Invoice` en **Parquet**. La partition `invoice_date` est facultative pour cette jointure ; elle montre aussi les dossiers par jour dans MinIO. Attendre **Terminée** dans **Historique**.
3. Choisir `crm / dbo.CustomerProfile`, extraire en **Parquet** sans partition, et attendre **Terminée**. Les deux jobs ont des préfixes MinIO distincts et deux tables `lake.billing.job_<id>`.
4. Dans **Éditeur SQL → Démo multi-source**, sélectionner les deux exports et cliquer **Préparer la jointure**, puis **Exécuter**. Le résultat regroupe les factures par segment CRM. **Voir les nœuds Trino** affiche le coordinateur et les deux workers dans le tableau SQL.
5. Sous le résultat de la jointure, cliquer **Tâches par worker**. Le tableau affiche les tâches et les fragments exécutés pour **cette requête** sur chaque nœud. Le coordinateur doit être absent de ce tableau de calcul ; les deux workers doivent y figurer.

La requête générée a cette forme, avec les vrais noms de tables obtenus dans l'Historique :

```sql
SELECT p.segment, count(*) AS factures, sum(i.amount) AS montant_total
FROM lake.billing.job_<id_invoice> AS i
JOIN lake.billing.job_<id_profile> AS p
  ON i.customer_id = p.customer_id
GROUP BY p.segment
ORDER BY montant_total DESC;
```

Le nom `lake.billing.job_<id>` désigne un **snapshot enregistré dans le catalogue Hive de Trino**. La requête ne relit pas SQL Server : chaque table est lue dans MinIO. Le bouton **Tâches par worker** utilise l'identifiant de requête retourné par l'API SQL. La même preuve est disponible dans l'interface Trino (`http://localhost:8080/`) ou avec cette requête :

```sql
SELECT node_id, count(*) AS tasks, sum(completed_splits) AS splits
FROM system.runtime.tasks
WHERE query_id = '<query_id>'
GROUP BY node_id
ORDER BY node_id;
```

## Vérification réalisée

Le 28 novembre 2026, les deux exports Parquet ont terminé avec **1 000 000 factures** et **100 000 profils**. La jointure a retourné quatre segments de **250 000 factures** chacun. Pour cette requête, `system.runtime.tasks` a montré des tâches et des fragments terminés sur **chacun des deux workers** (5 tâches/104 fragments et 6 tâches/105 fragments). Ces chiffres sont un exemple de campagne locale ; les durées et la répartition exacte peuvent changer à chaque exécution.
