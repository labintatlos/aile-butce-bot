#!/usr/bin/with-contenv bashio
# Add-on başlatma betiği.
#
# Home Assistant seçeneklerini ortam değişkenlerine aktarır ve uygulamayı
# başlatır. Bot token'ı hiçbir zaman ekrana veya loga yazılmaz.
set -e

readonly INGRESS_PORT=8099
readonly PUBLIC_PORT=8100
readonly DATA_DIR="/data"

cd /app

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
# `bashio::config` boş bırakılmış bir alan için boş dize değil **`null`**
# döndürür. Bu değer olduğu gibi aktarılırsa uygulama onu gerçek bir ayar
# sanar; açılışta çöker ve Supervisor günlüğünde yalnızca "exit code 1"
# görünür. Bu yüzden her isteğe bağlı alan önce değer taşıyıp taşımadığına
# göre kontrol edilir.
export_optional() {
  local key="${1}"
  local variable="${2}"
  if bashio::config.has_value "${key}"; then
    export "${variable}=$(bashio::config "${key}")"
  else
    export "${variable}="
  fi
}

export TELEGRAM_BOT_TOKEN
export AUTHORIZED_TELEGRAM_IDS
export_optional 'user_display_names' USER_DISPLAY_NAMES
export_optional 'ha_user_map' HA_USER_MAP
export_optional 'webapp_public_url' WEBAPP_PUBLIC_URL
export_optional 'timezone' TIMEZONE
export_optional 'log_level' LOG_LEVEL
export_optional 'backup_retention' BACKUP_RETENTION

[[ -z "${TIMEZONE}" ]] && export TIMEZONE="Europe/Istanbul"
[[ -z "${LOG_LEVEL}" ]] && export LOG_LEVEL="info"
[[ -z "${BACKUP_RETENTION}" ]] && export BACKUP_RETENTION="14"

export DATABASE_PATH="${DATA_DIR}/budget.db"
export FRONTEND_DIST="/app/frontend"
export DEBUG="false"
export ALLOW_DEV_AUTH="false"

mkdir -p "${DATA_DIR}/backups"

# --- Ön kontrol --------------------------------------------------------------
# Uygulamayi ice aktarmayi ve yapilandirmayi once sinamak, hatanin uvicorn'un
# yigin izinin altinda kaybolmasini engeller. Bir ayar yanlis yazildiginda
# kullanici hangi alanin bozuk oldugunu burada gorur.
bashio::log.info "Yapılandırma denetleniyor..."
if ! python -m app.cli config; then
  bashio::exit.nok "Yapılandırma hatalı. Yukarıdaki mesajda belirtilen ayarı düzeltin."
fi

# --- Veritabanı göçleri ------------------------------------------------------
bashio::log.info "Veritabanı göçleri uygulanıyor..."
if ! python -m alembic upgrade head; then
  bashio::exit.nok "Veritabanı göçü başarısız. Eklenti başlatılmadı, verilerinize dokunulmadı."
fi

# --- Uygulama ----------------------------------------------------------------
# İki farklı sunucu çalışabilir ve aralarındaki fark kasıtlıdır:
#
#   8099 (Ingress) : yalnızca Supervisor ağından erişilir, X-Remote-User-Id
#                    başlığına güvenir, Telegram botunu da bu süreç çalıştırır.
#   8100 (genel)   : internete açılabilir, başlığa güvenmez, yalnızca imzalı
#                    Telegram initData kabul eder.
#
# Bot yalnızca ilk süreçte açıktır: Telegram aynı bot için tek bir getUpdates
# tüketicisine izin verir, ikinci süreç sürekli çakışma hatası üretirdi.
#
# Genel sunucu arka planda, Ingress sunucusu `exec` ile ön planda çalışır.
# Böylece uvicorn'un hatası ve çıkış kodu doğrudan eklenti günlüğüne düşer;
# her ikisini de arka plana alıp `wait` ile beklemek, gerçek hatayı gizleyip
# her başarısızlığı anlamsız bir "exit code 1" hâline getiriyordu.

if bashio::var.has_value "${WEBAPP_PUBLIC_URL}"; then
  bashio::log.info "Telegram Mini App sunucusu başlatılıyor (port ${PUBLIC_PORT})"
  TRUST_INGRESS_HEADERS="false" ENABLE_BOT="false" \
    python -m uvicorn app.main:app \
    --host 0.0.0.0 --port "${PUBLIC_PORT}" --log-level "${LOG_LEVEL}" &
else
  bashio::log.info "webapp_public_url boş; Mini App sunucusu başlatılmadı. Arayüz Home Assistant panelinden kullanılabilir."
fi

bashio::log.info "Ingress arayüzü başlatılıyor (port ${INGRESS_PORT})"
export TRUST_INGRESS_HEADERS="true"
export ENABLE_BOT="true"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${INGRESS_PORT}" --log-level "${LOG_LEVEL}"
