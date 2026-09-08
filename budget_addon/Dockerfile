# syntax=docker/dockerfile:1

# --- 1. asama: arayuzu derle -------------------------------------------------
# Arayuz burada derlenir, calisma imajina yalnizca ciktisi kopyalanir. Boylece
# Raspberry Pi uzerinde Node calismaz ve calisma imaji kucuk kalir.
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
# npm ci: kilit dosyasindaki surumleri birebir kurar, derleme tekrarlanabilir olur.
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


# --- 2. asama: calisma imaji -------------------------------------------------
ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_PATH=/data/budget.db \
    FRONTEND_DIST=/app/frontend

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /build/dist ./frontend

COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Kalici veri yalnizca /data altindadir; HA'nin config klasorune erisilmez.
VOLUME /data

CMD ["/run.sh"]
