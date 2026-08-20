FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
COPY payment_service/ /app/payment_service
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY .env ./

RUN pip install -r requirements.txt --no-cache-dir

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
