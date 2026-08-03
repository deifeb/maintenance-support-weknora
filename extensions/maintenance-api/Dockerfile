FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY demand-engine /demand-engine
COPY maintenance-ai /maintenance-ai
COPY maintenance-api/requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir \
    -r /app/requirements.txt

COPY maintenance-api/app /app/app
COPY maintenance-api/alembic /app/alembic
COPY maintenance-api/alembic.ini /app/alembic.ini
COPY maintenance-api/config /app/config
COPY maintenance-api/templates /app/templates

RUN mkdir -p /app/data /app/exports

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
