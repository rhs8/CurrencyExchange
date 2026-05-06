FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends wget \
  && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api/src ./src
RUN mkdir -p /app/db_init
COPY db/init/002_users_journal.sql /app/db_init/002_users_journal.sql

CMD ["uvicorn", "iranx_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
