# BUILD_FROM ilk FROM'dan ONCE tanimlanmak zorundadir. Docker'da yalnizca ilk
# FROM'dan once bildirilen ARG'lar FROM satirinda kullanilabilir; asagi
# tasinirsa ${BUILD_FROM} bos dizeye acilir ve derleme anlasilmaz bir hatayla
# durur. Home Assistant Supervisor bu degeri build.yaml'dan gecirir.
ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.20

# --- 1. asama: arayuzu derle -------------------------------------------------
# Arayuz burada derlenir, calisma imajina yalnizca ciktisi kopyalanir. Boylece
# Raspberry Pi uzerinde Node calismaz ve calisma imaji kucuk kalir.
#
# Node surumu, package-lock.json'i ureten npm surumuyle ayni ana surumden
# secilir; eski bir npm yeni bicimli kilit dosyasinda takilabilir.
FROM node:24-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
# npm ci: kilit dosyasindaki surumleri birebir kurar, derleme tekrarlanabilir olur.
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


# --- 2. asama: calisma imaji -------------------------------------------------
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_PATH=/data/budget.db \
    FRONTEND_DIST=/app/frontend

WORKDIR /app

COPY backend/requirements.txt ./
# Alpine musl kullanir; bazi paketlerin bu platform icin hazir tekerlegi
# olmayabilir. Derleme araclari gecici olarak kurulur ve kurulum bitince
# silinir, boylece calisma imajinda yer kaplamazlar.
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /build/dist ./frontend

COPY run.sh /run.sh
RUN chmod a+x /run.sh

# VOLUME /data bilerek tanimlanmaz: kalici dizini Supervisor kendisi baglar ve
# imajda VOLUME bildirmek bu baglamayla catisabilir.

CMD ["/run.sh"]
