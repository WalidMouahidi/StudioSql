FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY data/seed.sql ./data/seed.sql
COPY data/seed_crm.sql ./data/seed_crm.sql
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
