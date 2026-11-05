FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends libpq5 \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
	&& python -c "import psycopg; from psycopg import pq; print('PostgreSQL client library:', pq.version())"

COPY app ./app
COPY frontend ./frontend

ENV APP_PERSISTENCE=database
ENV STORAGE_BACKEND=s3
ENV UPLOAD_DIR=/tmp/god-help-uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
