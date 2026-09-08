#!/usr/bin/with-contenv bashio
# Add-on başlatma betiği.
#
# Home Assistant seçeneklerini ortam değişkenlerine aktarır ve uygulamayı
# başlatır. Bot token'ı hiçbir zaman ekrana veya loga yazılmaz.
set -euo pipefail

readonly INGRESS_PORT=8099
readonly PUBLIC_PORT=8100
readonly DATA_DIR="/data"

# --- Zorunlu ayarlar ---------------------------------------------------------
TELEGRAM_BOT_TOKEN="$(bashio::config 'telegram_bot_token')"
AUTHORIZED_TELEGRAM_IDS="$(bashio::config 'authorized_telegram_ids')"

if bashio::var.is_empty "${TELEGRAM_BOT_TOKEN}"; then
  bashio::exit.nok "Telegram bot token girilmemiş. Eklenti ayarlarından 'telegram_bot_token' alanını doldurun."
fi

if bashio::var.is_empty "${AUTHORIZED_TELEGRAM_IDS}"; then
  bashio::exit.nok "Yetkili Telegram kullanıcıları belirtilmemiş. 'authorized_telegram_ids' alanına virgülle ayrılmış kimlikleri yazın."
fi

# --- İsteğe bağlı ayarlar ----------------------------------------------------
export TELEGRAM_BOT_TOKEN
export AUTHORIZED_TELEGRAM_IDS
export USER_DISPLAY_NAMES="$(bashio::config 'user_display_names')"
export HA_USER_MAP="$(bashio::config 'ha_user_map')"
export WEBAPP_PUBLIC_URL="$(bashio::config 'webapp_public_url')"
export TIMEZONE="$(bashio::config 'timezone')"
export LOG_LEVEL="$(bashio::config 'log_level')"
export BACKUP_RETENTION="$(bashio::config 'backup_retention')"

export DATABASE_PATH="${DATA_DIR}/budget.db"
export FRONTEND_DIST="/app/frontend"
export DEBUG="false"
export ALLOW_DEV_AUTH="false"

mkdir -p "${DATA_DIR}/backups"

# --- Veritabanı göçleri ------------------------------------------------------
bashio::log.info "Veritabanı göçleri uygulanıyor..."
cd /app
if ! python -m alembic upgrade head; then
  bashio::exit.nok "Veritabanı göçü başarısız. Eklenti başlatılmadı, verilerinize dokunulmadı."
fi

# --- Uygulama ----------------------------------------------------------------
# İki ayrı süreç çalışır ve aralarındaki fark kasıtlıdır:
#
#   8099 (Ingress) : yalnızca Supervisor ağından erişilir, X-Remote-User-Id
#                    başlığına güvenir, Telegram botunu da bu süreç çalıştırır.
#   8100 (genel)   : internete açılabilir, başlığa güvenmez, yalnızca imzalı
#                    Telegram initData kabul eder.
#
# Bot yalnızca ilk süreçte açıktır: Telegram aynı bot için tek bir getUpdates
# tüketicisine izin verir, ikinci süreç sürekli çakışma hatası üretirdi.

terminate() {
  bashio::log.info "Eklenti durduruluyor..."
  kill 0
}
trap terminate SIGTERM SIGINT

bashio::log.info "Ingress arayüzü başlatılıyor (port ${INGRESS_PORT})"
TRUST_INGRESS_HEADERS="true" ENABLE_BOT="true" \
  python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${INGRESS_PORT}" --log-level "${LOG_LEVEL}" &

if bashio::var.has_value "${WEBAPP_PUBLIC_URL}"; then
  bashio::log.info "Telegram Mini App sunucusu başlatılıyor (port ${PUBLIC_PORT})"
  TRUST_INGRESS_HEADERS="false" ENABLE_BOT="false" \
    python -m uvicorn app.main:app \
    --host 0.0.0.0 --port "${PUBLIC_PORT}" --log-level "${LOG_LEVEL}" &
else
  bashio::log.info "webapp_public_url boş; Mini App sunucusu başlatılmadı. Arayüz Home Assistant panelinden kullanılabilir."
fi

wait -n
bashio::log.warning "Süreçlerden biri sonlandı; eklenti kapanıyor."
terminate
