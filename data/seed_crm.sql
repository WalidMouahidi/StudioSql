SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID('dbo.CustomerProfile', 'U') IS NOT NULL RETURN;

CREATE TABLE dbo.CustomerProfile (
    customer_id int NOT NULL PRIMARY KEY,
    segment varchar(12) NOT NULL,
    loyalty_points int NOT NULL,
    region nvarchar(30) NOT NULL,
    updated_at date NOT NULL
);

DECLARE @customers int = %s;
WITH digits(n) AS (
    SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) d(n)
)
SELECT TOP (@customers) CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS n
INTO #numbers
FROM digits a CROSS JOIN digits b CROSS JOIN digits c
CROSS JOIN digits d CROSS JOIN digits e CROSS JOIN digits f ORDER BY n;

INSERT INTO dbo.CustomerProfile
SELECT n,
       CHOOSE(n % 4 + 1, 'standard', 'silver', 'gold', 'enterprise'),
       (n * 17) % 1000,
       CHOOSE(n % 4 + 1, N'Île-de-France', N'Auvergne-Rhône-Alpes', N'Hauts-de-France', N'Pays de la Loire'),
       DATEADD(day, n % 180, CONVERT(date, '2025-01-01'))
FROM #numbers;
