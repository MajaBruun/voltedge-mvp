# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# Installer afhængigheder i et separat lag (Docker cache-optimering)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopier kildekode
COPY app/ ./app/

# ── Runtime ──────────────────────────────────────────────────────────────────
# Secrets sættes som env-variabler ved runtime — aldrig bagt ind i image
# Eksempel: docker run -e PRICE_PER_KWH=2.50 -e DB_PATH=/data/voltedge.db ...

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
