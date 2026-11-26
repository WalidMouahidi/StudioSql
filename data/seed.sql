SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID('dbo.Payment', 'U') IS NOT NULL RETURN;

CREATE TABLE dbo.Customer (
    customer_id int NOT NULL PRIMARY KEY,
    first_name nvarchar(40) NOT NULL,
    last_name nvarchar(40) NOT NULL,
    email nvarchar(100) NOT NULL,
    city nvarchar(60) NOT NULL,
    created_at datetime2(3) NOT NULL
);
CREATE TABLE dbo.Invoice (
    invoice_id int NOT NULL PRIMARY KEY,
    customer_id int NOT NULL REFERENCES dbo.Customer(customer_id),
    invoice_date date NOT NULL,
    amount decimal(12,2) NOT NULL,
    status varchar(12) NOT NULL
);
CREATE TABLE dbo.Payment (
    payment_id int NOT NULL PRIMARY KEY,
    invoice_id int NOT NULL REFERENCES dbo.Invoice(invoice_id),
    payment_date date NOT NULL,
    amount decimal(12,2) NOT NULL,
    payment_method varchar(12) NOT NULL
);

DECLARE @total int = %s;
DECLARE @customers int = (@total + 9) / 10;

WITH digits(n) AS (
    SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) d(n)
)
SELECT TOP (@total) CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS n
INTO #numbers
FROM digits a CROSS JOIN digits b CROSS JOIN digits c CROSS JOIN digits d
CROSS JOIN digits e CROSS JOIN digits f ORDER BY n;

INSERT INTO dbo.Customer
SELECT n, CONCAT(N'Prénom ', n), CONCAT(N'Nom ', n),
       CONCAT('customer', n, '@example.test'),
       CHOOSE(n % 4 + 1, N'Paris', N'Lyon', N'Lille', N'Nantes'),
       DATEADD(day, n % 365, CONVERT(datetime2(3), '2024-01-01'))
FROM #numbers WHERE n <= @customers;

INSERT INTO dbo.Invoice
SELECT n, (n - 1) % @customers + 1,
       DATEADD(day, (n - 1) * 1.0 * 180 / @total, CONVERT(date, '2025-01-01')),
       (n % 100000 + 100) / 100.0, CHOOSE(n % 4 + 1, 'paid', 'paid', 'open', 'paid')
FROM #numbers;

INSERT INTO dbo.Payment
SELECT invoice_id, invoice_id, DATEADD(day, invoice_id % 7, invoice_date),
       amount, CHOOSE(invoice_id % 3 + 1, 'card', 'transfer', 'cash')
FROM dbo.Invoice WHERE status = 'paid';
