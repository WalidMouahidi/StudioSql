import json
import os


SOURCES = {source["id"]: source for source in json.loads(os.environ["SQL_SOURCES"])}
BUCKET = "warehouse"
SEED_SQL_PATH = "/app/data/seed.sql"
SEED_CRM_SQL_PATH = "/app/data/seed_crm.sql"
DAY_PARTITION_TYPES = {"date", "datetime", "datetime2", "smalldatetime"}
