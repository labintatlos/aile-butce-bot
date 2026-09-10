#!/usr/bin/with-contenv bashio
# Add-on başlatma betiği.
#
# Home Assistant seçeneklerini ortam değişkenlerine aktarır ve uygulamayı
# başlatır. Şifreler hiçbir zaman ekrana veya loga yazılmaz.
set -e

readonly INGRESS_PORT=8099
readonly PUBLIC_PORT=8100
readonly DATA_DIR="/data"

cd /app

# --- Ayarlar -----------------------------------------------------------------
# Hiçbir ayar zorunlu değildir: ilk yönetici sitede kurulum koduyla oluşturulur.
#
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

export_optional 'site_url' SITE_URL
export_optional 'ha_user_map' HA_USER_MAP
export_optional 'timezone' TIMEZONE
export_optional 'log_level' LOG_LEVEL
export_optional 'backup_retention' BACKUP_RETENTION
export_optional 'enable_reminders' ENABLE_REMINDERS
export_optional 'reminder_hour' REMINDER_HOUR
export_optional 'due_reminder_days' DUE_REMINDER_DAYS
export_optional 'smtp_host' SMTP_HOST
export_optional 'smtp_port' SMTP_PORT
export_optional 'smtp_security' SMTP_SECURITY
export_optional 'smtp_username' SMTP_USERNAME
export_optional 'smtp_password' SMTP_PASSWORD
export_optional 'smtp_sender' SMTP_SENDER
export_optional 'publish_ha_sensors' PUBLISH_HA_SENSORS
export_optional 'ha_publish_interval_minutes' HA_PUBLISH_INTERVAL_MINUTES

[[ -z "${TIMEZONE}" ]] && export TIMEZONE="Europe/Istanbul"
[[ -z "${LOG_LEVEL}" ]] && export LOG_LEVEL="info"
[[ -z "${BACKUP_RETENTION}" ]] && export BACKUP_RETENTION="14"
[[ -z "${ENABLE_REMINDERS}" ]] && export ENABLE_REMINDERS="true"
[[ -z "${REMINDER_HOUR}" ]] && export REMINDER_HOUR="9"
[[ -z "${DUE_REMINDER_DAYS}" ]] && export DUE_REMINDER_DAYS="3"
[[ -z "${SMTP_PORT}" ]] && export SMTP_PORT="587"
[[ -z "${SMTP_SECURITY}" ]] && export SMTP_SECURITY="starttls"
[[ -z "${PUBLISH_HA_SENSORS}" ]] && export PUBLISH_HA_SENSORS="true"
[[ -z "${HA_PUBLISH_INTERVAL_MINUTES}" ]] && export HA_PUBLISH_INTERVAL_MINUTES="15"

# Supervisor bu degiskeni ortama kendisi koyar; uygulama onu Home Assistant'a
# sensor yazarken kullanir. Boşsa (eklenti disinda calisiyorsa) yayim atlanir.
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN:-}"

export DATABASE_PATH="${DATA_DIR}/budget.db"
export FRONTEND_DIST="/app/frontend"
export DEBUG="false"

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
# İki sunucu çalışır ve aralarındaki fark kasıtlıdır:
#
#   8100 (web sitesi) : internete açılır (KeenDNS), başlığa güvenmez; kimlik
#                       yalnızca kullanıcı adı/şifreyle verilen oturum
#                       çerezinden gelir.
#   8099 (Ingress)    : yalnızca Supervisor ağından erişilir, X-Remote-User-Id
#                       başlığına güvenir. Hatırlatmalar ve sensör yayımı bu
#                       süreçte çalışır; iki süreçte birden çalışsalardı iş
#                       iki kez yapılırdı.
#
# Web sitesi arka planda, Ingress sunucusu `exec` ile ön planda çalışır.
# Böylece uvicorn'un hatası ve çıkış kodu doğrudan eklenti günlüğüne düşer;
# her ikisini de arka plana alıp `wait` ile beklemek, gerçek hatayı gizleyip
# her başarısızlığı anlamsız bir "exit code 1" hâline getiriyordu.

bashio::log.info "Web sitesi sunucusu başlatılıyor (port ${PUBLIC_PORT})"
TRUST_INGRESS_HEADERS="false" RUN_BACKGROUND_JOBS="false" \
  python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${PUBLIC_PORT}" --log-level "${LOG_LEVEL}" &

bashio::log.info "Home Assistant paneli başlatılıyor (port ${INGRESS_PORT})"
export TRUST_INGRESS_HEADERS="true"
export RUN_BACKGROUND_JOBS="true"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${INGRESS_PORT}" --log-level "${LOG_LEVEL}"
