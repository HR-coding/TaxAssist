# syntax=docker/dockerfile:1
# Single-container TaxAssist: builds the React frontend, then serves it from FastAPI
# alongside the API. One image, one Cloud Run / Render service.

# ── 1. Build the React frontend ──────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin API in production (BASE defaults to "" → calls go to "/me" on this server).
RUN npm run build

# ── 2. Install Python deps ───────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── 3. Runtime ───────────────────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /install /usr/local
COPY app ./app
# Bundle the built SPA so FastAPI can serve it at "/".
COPY --from=frontend /frontend/dist ./app/static
EXPOSE 8080
# Honors Cloud Run's injected $PORT (defaults to 8080).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*
