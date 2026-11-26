# Comparaison sur Invoice

Chaque scénario a été chargé une fois. Les temps SQL sont les médianes de 3 exécutions après une exécution de chauffe.

| Format | Compression | Partition | Lot | Lignes | Fichiers | Octets stockés | Extraction (s) | Chargement (s) | SQL global (s) | SQL filtré (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| csv | gzip | jour | 5000 | 1000000 | 360 | 5996043 | 5.487 | 23.470 | 1.730 | 0.790 |
| csv | gzip | jour | 50000 | 1000000 | 180 | 5977856 | 8.823 | 32.876 | 4.021 | 0.532 |
| csv | gzip | non | 5000 | 1000000 | 200 | 7128689 | 4.737 | 18.101 | 0.908 | 1.179 |
| csv | gzip | non | 50000 | 1000000 | 20 | 7114879 | 4.870 | 15.812 | 0.595 | 0.478 |
| csv | none | jour | 5000 | 1000000 | 360 | 32670846 | 6.429 | 42.079 | 3.841 | 0.465 |
| csv | none | jour | 50000 | 1000000 | 180 | 32670846 | 7.047 | 14.924 | 3.633 | 0.570 |
| csv | none | non | 5000 | 1000000 | 200 | 45670846 | 4.909 | 11.054 | 1.462 | 0.845 |
| csv | none | non | 50000 | 1000000 | 20 | 45670846 | 12.211 | 6.467 | 2.483 | 6.409 |
| parquet | gzip | jour | 5000 | 1000000 | 360 | 9817464 | 5.479 | 16.293 | 1.974 | 0.408 |
| parquet | gzip | jour | 50000 | 1000000 | 180 | 9884323 | 6.712 | 17.603 | 2.727 | 0.630 |
| parquet | gzip | non | 5000 | 1000000 | 200 | 9927069 | 4.856 | 6.603 | 0.393 | 0.539 |
| parquet | gzip | non | 50000 | 1000000 | 20 | 10712676 | 6.026 | 7.138 | 0.497 | 0.622 |
| parquet | none | jour | 5000 | 1000000 | 360 | 19175700 | 6.321 | 14.088 | 2.028 | 0.402 |
| parquet | none | jour | 50000 | 1000000 | 180 | 19241240 | 13.720 | 15.328 | 1.507 | 0.264 |
| parquet | none | non | 5000 | 1000000 | 200 | 19314920 | 6.132 | 6.722 | 1.235 | 0.445 |
| parquet | none | non | 50000 | 1000000 | 20 | 20165220 | 5.585 | 4.453 | 0.603 | 0.359 |

## Observations

- **Parquet / CSV, lecture globale**. Rapport médian de 0.60 sur 8 paires. Parquet permet de lire la colonne amount seule. Le lecteur CSV doit parcourir les lignes et convertir amount.
- **Partitionné / non partitionné, filtre de date**. Rapport médian de 0.75 sur 8 paires. Trino peut écarter les autres jours. L'ouverture de fichiers et le catalogue ont un coût fixe.
- **Gzip / sans compression, taille stockée**. Rapport médian de 0.35 sur 8 paires. Gzip réduit les octets écrits. Consulter aussi le chargement pour observer le coût de compression.
- **Grand lot / petit lot, nombre de fichiers**. Rapport médian de 0.30 sur 8 paires. Un grand lot peut réduire le nombre de fichiers. Chaque jour reste un dossier distinct lorsqu'il est partitionné.

## Lecture des résultats de cette exécution

- Le partitionnement quotidien a réduit de 25 % le temps médian de la requête filtrée sur les paires comparables. Le chargement a pris 2,39 fois plus de temps et la lecture globale 2,56 fois plus de temps. La création de 180 à 360 fichiers et l’enregistrement des partitions ajoutent du travail au chargement. Le tri côté SQL Server intervient pendant l’extraction.
- Avec Gzip, les scénarios ont occupé 65 % d’espace en moins et le chargement a pris 38 % de temps en plus en médiane par paire. Le plus petit export est le CSV Gzip partitionné par jour avec un lot de 50 000 lignes, à 5 977 856 octets. La structure colonnaire de Parquet est utile pour la lecture de colonnes ciblées, tandis que Gzip peut exploiter les répétitions du texte CSV sur ce jeu synthétique.
- Sans partitionnement, le lot de 50 000 a produit 20 fichiers contre 200 pour le lot de 5 000. Le rapport médian des temps de chargement est resté proche de 1 (0,98) sur l’ensemble des paires. Le nombre de fichiers et le temps total de chargement varient aussi avec le format, la compression et le partitionnement.
- Les temps d’extraction vont de 4,74 à 13,72 s. Les opérations alternent lecture, encodage et transfert. Les temps du client SQL Server incluent le tri des variantes partitionnées et peuvent varier avec la charge locale. Chaque extraction a été mesurée une fois.
