# Aile Bütçe ve Harcama Takip Sistemi — Uygulama Planı

> **Tarihsel belge.** 2.0.0 sürümüyle Telegram botu ve Mini App kaldırıldı;
> sistem artık kullanıcı adı ve şifreyle açılan bir web sitesidir. Aşağıdaki
> Telegram'a dair bölümler ilk planı kayıt için korur. Güncel kurulum için
> `budget_addon/DOCS.md` ve `docs/DEPLOYMENT_HA.md` geçerlidir.

Bu doküman kod yazılmadan önce mimariyi, veri modelini, hesaplama akışını,
güvenlik modelini, dağıtım yaklaşımını, geliştirme aşamalarını, riskleri ve
kabul kriterlerini sabitler. Onaylandıktan sonra implementasyon bu plana göre
ilerler.

---

## 0. Başlangıç durumu ve konum kararı

Çalışma ağacında daha önce başlanmış üç bütçe denemesi bulundu:

| Klasör | Durum |
|---|---|
| `../BÜTÇE TAKİP` | ~694 satır iskelet + `venv` + boş veritabanı |
| `../family-budget` | ~889 satır iskelet, finans çekirdeği doğru |
| `../family-budget-addon-flat-v1.0.4` | `family-budget` ile birebir aynı kopya |

`BÜTÇE TAKİP/backend/data/budget.db` incelendi: yalnızca 16 seed kategori var,
`users` / `payment_methods` / `expenses` / `expense_installments` tablolarının
tamamı **boş**. Korunması gereken canlı finansal veri yoktur, dolayısıyla temiz
bir kurulum veri kaybı riski taşımaz.

**Karar:** Proje `TELEGRAM BOTLARI GELİŞTİRME/BÜTÇE TAKİP SIFIRDAN/` altında
yeni ve kendi git deposu olan bir proje olarak kurulur. Eski üç klasör silinmez,
oldukları yerde referans olarak kalır.

**Devralınacak kod** (sıfırdan yazılmayacak, taşınıp genişletilecek):

- `family-budget/backend/app/services/finance/dates.py` — ay sonu normalizasyonu
  ve `add_months`; şartnamedeki §11 kuralına birebir uyuyor.
- `family-budget/backend/app/services/finance/engine.py` — ilk ekstre tarihi,
  son ödeme tarihi ve taksit planı üretimi; §10, §12, §13 kurallarına uyuyor.
- `family-budget/backend/app/services/finance/money.py` — kuruş dönüşümü,
  kayıpsız taksit bölme, Türkçe para formatı; §5, §9 kurallarına uyuyor.
- `family-budget/backend/app/security.py` — Telegram `initData` HMAC doğrulaması;
  §16, §31 kurallarına uyuyor.

Bu dosyalar yeni yapıya taşınırken katmanlara bölünecek, tip ve hata mesajları
korunacak, üzerlerine §37'deki tam test seti yazılacak.

---

## 1. Mimari

Tek bir Python süreci, tek bir SQLite veritabanı, tek bir HTTP portu.

```
                     +------------------------------------+
   Telegram  ------> |  aiogram (long polling)            |
   istemcisi         |  bot/ - sadece sunum ve yonlendirme|
                     +---------------+--------------------+
                                     |
   HA uygulamasi      +--------------v--------------------+
   (Ingress)   -----> |  FastAPI                          |
   Telegram           |  api/      - HTTP arayuzu         |
   Mini App    -----> |  security/ - 3 kimlik kaynagi:    |
   Yerel gelistirme   |    Ingress | initData | dev       |
   (dev)       -----> +--------------+--------------------+
                                     |  (tek ortak yol)
                      +--------------v--------------------+
                      |  services/  - is kurallari        |
                      |    finance/ - deterministik motor |
                      +--------------+--------------------+
                                     |
                      +--------------v--------------------+
                      |  repositories/ - sorgular         |
                      |  models/       - SQLAlchemy 2.x   |
                      +--------------+--------------------+
                                     |
                            SQLite (WAL, /data/budget.db)
```

Kurallar:

- Bot handler'ları ve API route'ları **iş kuralı içermez**. İkisi de aynı
  `services` fonksiyonlarını çağırır; farkları yalnızca girdi ayrıştırma ve
  çıktı biçimlendirmedir. Böylece "bottan girilen harcama" ile "Mini App'ten
  girilen harcama" arasında hesaplama farkı oluşamaz.
- `services/finance/` saf fonksiyonlardan oluşur: veritabanı, ağ veya zaman
  bağımlılığı yoktur; girdileri argüman olarak alır. Bu modül tek başına test
  edilebilir ve testleri projenin geçiş kapısıdır.
- Finansal hesaplamada LLM veya olasılıksal hiçbir bileşen kullanılmaz.
  Yapay zekâ ileride yalnızca hazır deterministik raporun doğal dilde
  yorumlanması için, opsiyonel ve varsayılan olarak kapalı bir katman şeklinde
  eklenir.
- aiogram polling görevi FastAPI'nin `lifespan` bağlamında başlatılır ve
  kapanışta düzgün durdurulur. Webhook kullanılmaz.
- Derlenmiş web arayüzü varlıkları aynı FastAPI süreci tarafından `/app`
  altından statik olarak sunulur.

### Tek arayüz, üç bağlam

Harcama giriş formu **bir kez** yazılır ve üç farklı bağlamda aynı kodla
çalışır. Fark yalnızca kimliğin nereden geldiğidir; arayüz kodu ve iş kuralları
birebir aynıdır.

| Bağlam | Kimlik kaynağı | Altyapı gereksinimi | Giriş noktası |
|---|---|---|---|
| **Home Assistant Ingress** | `X-Remote-User-Id` başlığı (HA doğrular) | **Yok** | HA uygulaması → kenar çubuğu |
| **Telegram Mini App** | `initData` HMAC doğrulaması | Public HTTPS (Cloudflare Tunnel vb.) | Bot → `➕ Harcama Ekle` |
| **Yerel geliştirme** | `X-Dev-Telegram-User-Id` başlığı | Yok | Tarayıcı |

Sunucu tarafında bu, `security/` altında tek bir FastAPI bağımlılığıdır: üç
kaynağı sırayla dener, ilk geçerli olanı kabul eder, hiçbiri yoksa `401` döner.
Dev kaynağı yalnızca `ALLOW_DEV_AUTH=true` iken etkindir ve üretim
yapılandırmasında kapalıdır.

Bu tasarımın amacı R1 riskini bloke edici olmaktan çıkarmaktır: sistem Ingress
ile ilk günden altyapı işi olmadan kullanılabilir; tünel kurulduğunda aynı sayfa
Telegram Mini App olarak da açılır ve **hiçbir kod değişmez**, yalnızca
`WEBAPP_PUBLIC_URL` yapılandırılır.

Arayüz Ingress altında bir yol öneki (`/api/hassio_ingress/<token>/`) ile
sunulduğu için Vite `base: './'` ile derlenir ve tüm API çağrıları göreli
adreslerle yapılır. Mutlak yol (`/api/...`) hiçbir yerde kullanılmaz.

### Süreç içi görev dağılımı

| Görev | Nerede |
|---|---|
| Telegram komutları, menüler, rapor mesajları | `bot/` |
| Hızlı metin girişi ayrıştırma | `services/quick_entry.py` |
| Web arayüzü REST uçları | `api/` |
| Ingress / initData / dev kimlik doğrulama, yetki kontrolü | `security/` |
| Harcama oluşturma/güncelleme/silme iş akışı | `services/expenses.py` |
| Rapor toplama | `services/reports.py` |
| Taksit/ekstre matematiği | `services/finance/` |
| Yedekleme | `services/backup.py` |
| Denetim kaydı | `services/audit.py` |

---

## 2. Repository ağacı

Depo aynı zamanda bir **Home Assistant custom add-on deposudur**. Bu yüzden
kökte `repository.yaml` bulunur ve add-on'un tamamı tek bir alt klasörde toplanır
(`su-urunleri-bot` deposundaki düzenin aynısı). Home Assistant depoyu bu yapıya
göre tarar.

```
aile-butce-bot/                      <- GitHub deposunun koku (public)
├── repository.yaml                  <- HA add-on deposu tanimi
├── README.md
├── IMPLEMENTATION_PLAN.md
├── .gitignore
├── docker-compose.yml               # yerel gelistirme
├── docs/
│   ├── DATA_MODEL.md                # ER şeması ve tablo sözleşmeleri
│   ├── FINANCE_RULES.md             # taksit/ekstre kuralları ve örnekleri
│   ├── SECURITY.md                  # tehdit modeli ve doğrulama akışı
│   ├── DEPLOYMENT_HA.md             # HA + KeenDNS kurulumu
│   └── TEST_SCENARIOS.md            # §37 senaryolarının izlenebilir listesi
└── budget_addon/                    <- ADD-ON KOKU (HA burayi okur)
    ├── config.yaml                  # add-on tanimi, ingress + portlar
    ├── build.yaml                   # aarch64 temel imaj
    ├── Dockerfile                   # cok asamali: node build -> python runtime
    ├── run.sh                       # bashio ile config -> ortam degiskeni
    ├── DOCS.md                      # kullaniciya gorunen kurulum belgesi
    ├── CHANGELOG.md
    ├── .env.example                 # yalnizca yer tutucu, gercek sir yok
    ├── backend/
    │   ├── requirements.txt
    │   ├── requirements-dev.txt
    │   ├── pytest.ini
    │   ├── alembic.ini
    │   ├── app/
    │   │   ├── main.py              # FastAPI + lifespan + polling gorevi
    │   │   ├── config.py            # pydantic-settings, ortam degiskenleri
    │   │   ├── database.py          # async engine, session, PRAGMA'lar
    │   │   ├── logging_config.py    # yapilandirilmis log, gizli veri maskesi
    │   │   ├── cli.py               # python -m app.cli backup | seed | migrate
    │   │   ├── models/
    │   │   │   ├── base.py
    │   │   │   ├── user.py
    │   │   │   ├── payment_method.py
    │   │   │   ├── category.py
    │   │   │   ├── expense.py
    │   │   │   ├── installment.py
    │   │   │   └── audit_log.py
    │   │   ├── schemas/
    │   │   │   ├── common.py        # para ve tarih tipleri
    │   │   │   ├── expense.py
    │   │   │   ├── payment_method.py
    │   │   │   ├── category.py
    │   │   │   └── report.py
    │   │   ├── repositories/
    │   │   │   ├── expense_repository.py
    │   │   │   ├── installment_repository.py
    │   │   │   ├── payment_method_repository.py
    │   │   │   ├── category_repository.py
    │   │   │   ├── user_repository.py
    │   │   │   └── audit_repository.py
    │   │   ├── services/
    │   │   │   ├── expenses.py      # olustur/guncelle/sil, tek transaction
    │   │   │   ├── reports.py       # aylik, ekstre, taksit, gelecek yuk
    │   │   │   ├── quick_entry.py   # "500 market" metnini ayristirma
    │   │   │   ├── search.py
    │   │   │   ├── settings_service.py
    │   │   │   ├── audit.py
    │   │   │   ├── backup.py
    │   │   │   └── finance/
    │   │   │       ├── money.py         # kurus donusumu, kayipsiz bolme, format
    │   │   │       ├── dates.py         # ay sonu normalizasyonu, add_months
    │   │   │       ├── statement.py     # ilk ekstre ve son odeme tarihi
    │   │   │       ├── installments.py  # taksit plani uretimi
    │   │   │       └── reports.py       # saf toplama/gruplama yardimcilari
    │   │   ├── api/
    │   │   │   ├── deps.py
    │   │   │   ├── errors.py
    │   │   │   └── routes/
    │   │   │       ├── expenses.py
    │   │   │       ├── payment_methods.py
    │   │   │       ├── categories.py
    │   │   │       ├── reports.py
    │   │   │       └── meta.py      # /health, /bootstrap
    │   │   ├── bot/
    │   │   │   ├── runner.py
    │   │   │   ├── middlewares/authorization.py
    │   │   │   ├── keyboards.py
    │   │   │   ├── formatting.py    # Turkce para/tarih bicimlendirme
    │   │   │   └── handlers/
    │   │   │       ├── menu.py
    │   │   │       ├── monthly.py
    │   │   │       ├── statements.py
    │   │   │       ├── installments.py
    │   │   │       ├── upcoming.py
    │   │   │       ├── analysis.py
    │   │   │       ├── search.py
    │   │   │       ├── settings.py
    │   │   │       ├── quick_entry.py       # "500 market" kisayolu
    │   │   │       └── expense_actions.py   # duzenle / sil onayi
    │   │   ├── security/
    │   │   │   ├── identity.py      # port bazli kimlik cozumleme
    │   │   │   ├── telegram_auth.py # initData HMAC dogrulamasi
    │   │   │   ├── ingress_auth.py  # X-Remote-User-Id eslemesi
    │   │   │   └── authorization.py
    │   │   └── utils/
    │   │       ├── public_id.py
    │   │       └── time.py          # Europe/Istanbul "bugun"
    │   ├── migrations/
    │   │   ├── env.py
    │   │   └── versions/
    │   └── tests/
    │       ├── conftest.py
    │       ├── unit/
    │       │   ├── test_money.py
    │       │   ├── test_dates.py
    │       │   ├── test_statement.py
    │       │   ├── test_installments.py
    │       │   └── test_quick_entry.py
    │       ├── integration/
    │       │   ├── test_expense_lifecycle.py
    │       │   ├── test_reports.py
    │       │   └── test_authorization.py
    │       └── acceptance/
    │           └── test_specification_cases.py   # §38, §39, §40
    └── frontend/
        ├── package.json
        ├── vite.config.ts           # base: './' (Ingress yol oneki icin)
        ├── tsconfig.json
        ├── index.html
        └── src/
            ├── main.tsx
            ├── App.tsx
            ├── api/client.ts
            ├── telegram/webapp.ts
            ├── components/
            │   ├── AmountInput.tsx
            │   ├── DateField.tsx
            │   ├── PaymentMethodPicker.tsx
            │   ├── InstallmentPicker.tsx
            │   ├── CategoryPicker.tsx
            │   ├── DescriptionField.tsx
            │   └── SchedulePreview.tsx
            ├── lib/format.ts
            └── styles/
```

`repository.yaml` içeriği:

```yaml
name: "Aile Bütçe Eklentileri"
url: "https://github.com/labintatlos/aile-butce-bot"
maintainer: "labintatlos <aykutcemc@gmail.com>"
```

**Depo public'tir** çünkü Home Assistant custom add-on depolarını kimlik
doğrulaması yapmadan klonlar. Bu nedenle depoya hiçbir sır girmez: bot token'ı,
Telegram kullanıcı kimlikleri, HA kullanıcı eşlemesi ve KeenDNS adresi yalnızca
add-on ayarlarında yaşar; depoda bunların yalnızca `.env.example` içinde yer
tutucuları bulunur.

---

## 3. Veritabanı şeması

Ayrıntılı sözleşmeler `docs/DATA_MODEL.md` içindedir. Özet ilişkiler:

```
users 1 ---< expenses >--- 1 categories
  |              |
  |              +---< expense_installments
  |
  +---< payment_methods ---< expenses

audit_logs (bagimsiz; entity_type + entity_id ile isaret eder)
```

Kritik sütunlar:

- Tüm para alanları `INTEGER` ve **kuruş** cinsindedir. Şemada `REAL`/`FLOAT`
  hiçbir yerde kullanılmaz.
- `expenses` tablosu, harcama oluşturulduğu andaki kart koşullarının
  anlık görüntüsünü (`statement_day_snapshot`, `due_day_snapshot`,
  `cutoff_inclusive_snapshot`) taşır. Kart ayarı sonradan değişse bile geçmiş
  taksit planı yeniden hesaplanmaz.
- `expenses.deleted_at` ile yumuşak silme yapılır; tüm rapor sorguları
  `deleted_at IS NULL` filtresini repository katmanında zorunlu kılar.
- `expense_installments` satırları harcamayla **aynı transaction** içinde yazılır.

---

## 4. Harcama → Taksit → Ekstre akışı

```
Kullanici girdisi
  tutar "1.250,50"  tarih 2026-09-08  yontem #3  taksit 3  kategori #1
        |
        v
[1] Dogrulama (Pydantic)
        tutar Decimal olarak ayristirilir, 2 basamaga ROUND_HALF_UP ile yuvarlanir
        installment_count 1..12
        transaction_date makul aralikta
        |
        v
[2] Kurusa cevirme          total_amount_minor = 125050
        |
        v
[3] Odeme yontemi okunur ve anlik goruntu alinir
        type=credit_card, statement_day=10, due_day=20, cutoff_inclusive=true
        type=cash ise installment_count 1'e zorlanir, aksi halde hata
        |
        v
[4] Tutar kayipsiz bolunur         split_minor(125050, 3)
        base, remainder = divmod(125050, 3) -> 41683, 1
        [41684, 41683, 41683]      toplam = 125050   <- degismez kural
        |
        v
[5] Ilk ekstre tarihi              first_statement_date(2026-09-08, 10, true)
        aday = normalize(2026, 09, 10) = 2026-09-10
        islem < aday  ->  aday kabul edilir  ->  2026-09-10
        |
        v
[6] Her taksit icin ekstre ve son odeme tarihi
        ekstre_n  = add_months(ilk_ekstre, n-1, statement_day)
        son_odeme = add_months(ekstre_n, (0 if due_day > statement_day else 1), due_day)
        Her iki tarihte de ay sonu normalizasyonu uygulanir.
        |
        v
[7] Tek transaction: expense INSERT + N adet installment INSERT + audit INSERT
        Hepsi basarili -> COMMIT      Herhangi biri basarisiz -> ROLLBACK
        |
        v
[8] public_id uretimi (EXP-000184) ve Telegram onay mesaji
```

Raporlama tarafında iki bakış **hiçbir zaman** aynı toplama karışmaz:

| Bakış | Kaynak | Tarih alanı |
|---|---|---|
| Harcama (spending) | `expenses.total_amount_minor` | `transaction_date` |
| Nakit akışı — ekstre bazlı | `expense_installments.amount_minor` | `statement_date` |
| Nakit akışı — son ödeme bazlı | `expense_installments.amount_minor` | `due_date` |

API uç adları bu ayrımı isimde taşır: `/reports/spending/monthly`,
`/reports/cashflow/statements`, `/reports/cashflow/upcoming`.

---

## 5. Güvenlik modeli

Katmanlar:

1. **Telegram bot tarafı.** Her güncelleme, handler'lara ulaşmadan önce bir
   aiogram middleware'inden geçer. `from_user.id` yapılandırmadaki
   `AUTHORIZED_TELEGRAM_IDS` listesinde yoksa güncelleme düşürülür ve kullanıcıya
   yalnızca `⛔ Bu botu kullanma yetkiniz bulunmuyor.` yanıtı döner. Yetkisiz
   kullanıcı hiçbir finansal veri, hiçbir buton ve hiçbir menü göremez.

2. **Home Assistant Ingress tarafı.** HA, kullanıcıyı kendi oturum sistemiyle
   doğrular ve isteği add-on'a proxy'lerken `X-Remote-User-Id` ile
   `X-Remote-User-Display-Name` başlıklarını ekler. Sunucu:
   - Bu başlıkları **yalnızca** istek Supervisor'ın Ingress ağından geldiğinde
     kabul eder; dışarıdan uydurulmuş başlık geçerli sayılmaz. Bu nedenle
     `ingress_port` doğrudan dışarıya açılmaz ve `ports` haritası boş bırakılır.
   - HA kullanıcı kimliğini `HA_USER_MAP` yapılandırmasıyla (`ha_user_id:telegram_id`)
     yerel `users` satırına eşler. Eşleşme yoksa `403` döner.

   Ingress bağlamı bot token'ı gerektirmez; kimlik tamamen HA'nın kendi
   doğrulamasına dayanır. Bu, Mini App için public HTTPS adresi kurulmadan da
   sistemin güvenle kullanılabilmesini sağlar.

3. **Mini App tarafı.** İstemci `Authorization: tma <initData>` başlığını
   gönderir. Sunucu:
   - `hash` alanını ayırır, kalan alanları `key=value` biçiminde sıralayıp
     `\n` ile birleştirir,
   - `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)` türetir,
   - `HMAC_SHA256(secret, data_check_string)` ile beklenen hash'i hesaplar ve
     `hmac.compare_digest` ile karşılaştırır,
   - `auth_date` tazeliğini kontrol eder (varsayılan 24 saat),
   - çözümlenen `user.id` değerini yetkili liste ile karşılaştırır,
   - veritabanında aktif bir `users` satırı bulunduğunu doğrular.

   `initDataUnsafe` kimlik doğrulama amacıyla asla kullanılmaz; yalnızca
   istemci tarafında tema ve isim gösterimi için okunur.

4. **Yetkilendirme.** Doğrulama başarılıysa istek bir `User` nesnesine bağlanır.
   Harcamanın `created_by_user_id` alanı istemciden **alınmaz**, doğrulanmış
   kimlikten türetilir. Böylece bir kullanıcı diğerinin adına kayıt oluşturamaz.

5. **Sır yönetimi.** Bot token yalnızca ortam değişkeninden okunur; depoya
   yazılmaz, `.env.example` içinde yalnızca yer tutucu bulunur. Log
   biçimlendiricisi token ve `initData` değerlerini maskeler; hata kayıtlarında
   ham `Authorization` başlığı yer almaz.

6. **Taşıma ve CORS.** `CORS_ALLOWED_ORIGINS` yalnızca `WEBAPP_PUBLIC_URL`
   kaynağını içerir; joker karakter kullanılmaz. Üretimde `DEBUG=false`,
   FastAPI `/docs` ve `/redoc` kapalıdır.

7. **Girdi doğrulama ve enjeksiyon.** Tüm girdiler Pydantic ile doğrulanır.
   Tüm sorgular SQLAlchemy ifadeleriyle, parametre bağlama ile kurulur; dize
   birleştirme ile SQL üretilmez. Arama metni `LIKE` parametresi olarak bağlanır
   ve joker karakterleri kaçırılır.

8. **Hata yüzeyi.** Kullanıcıya yığın izi gösterilmez. Beklenmeyen hatada bot
   `⚠️ İşlem kaydedilemedi. Verileriniz kaydedilmedi. Lütfen tekrar deneyin.`
   der, API `500` ve genel bir gövde döner, gerçek hata sunucu logunda kalır ve
   transaction geri alınır.

**Kapsam dışı (bilinçli):** Bu sistem iki kişilik özel bir kurulumdur; rol
tabanlı ayrıntılı yetki, çok kiracılı izolasyon ve istek hız sınırlama MVP'ye
dahil edilmez.

---

## 6. Home Assistant OS dağıtımı

Add-on tek konteyner olarak çalışır ve Raspberry Pi 5 için `aarch64` hedefler.

`homeassistant-addon/config.yaml` ana hatları:

```yaml
name: Aile Bütçe Takip
version: "1.0.0"
slug: family_budget
arch: [aarch64]
startup: services
boot: auto
init: false
ingress: true           # arayuz HA'nin kendi oturumu ile sunulur
ingress_port: 8099
panel_icon: mdi:wallet
panel_title: Bütçe
ports: {}               # port disariya acilmaz
map: []                 # HA config klasorune erisim istenmez
options:
  telegram_bot_token: ""
  authorized_telegram_ids: ""
  ha_user_map: ""       # "<ha_user_id>:<telegram_id>,..."
  webapp_public_url: "" # bos birakilabilir; Mini App icin gerekli
  timezone: Europe/Istanbul
  log_level: info
  backup_retention: 14
schema:
  telegram_bot_token: password
  authorized_telegram_ids: str
  ha_user_map: str?
  webapp_public_url: str?
  timezone: str
  log_level: list(debug|info|warning|error)
  backup_retention: int(1,365)
```

`ingress: true` sayesinde arayüz, HA kenar çubuğunda "Bütçe" paneli olarak
görünür ve HA'nın kendi HTTPS'i ile kendi oturum doğrulaması üzerinden açılır.
Bunun için tünel, alan adı, sertifika veya port yönlendirme **gerekmez**.
`ports` haritası bilinçli olarak boştur: uygulama yalnızca Supervisor'ın Ingress
ağından erişilebilir, böylece `X-Remote-User-Id` başlığı dışarıdan taklit
edilemez.

`webapp_public_url` boş bırakılabilir. Boşken bot menüsündeki
`➕ Harcama Ekle` düğmesi Mini App yerine hızlı metin girişi yönergesini ve
Ingress paneline yönlendirmeyi gösterir; doldurulduğunda aynı düğme Mini App'i
açar. Kod değişikliği gerekmez.

- Kalıcı veri yalnızca add-on'un kendi `/data` dizinindedir; veritabanı
  `/data/budget.db`, yedekler `/data/backups/`. HA'nın `config`, `ssl`,
  `share` veya `media` klasörlerine erişim **istenmez** (en az yetki ilkesi).
- `run.sh`, `bashio::config` ile okuduğu değerleri `export` ederek uygulamaya
  aktarır; token değeri hiçbir zaman `echo` edilmez. Zorunlu alanlar boşsa
  `bashio::exit.nok` ile anlaşılır bir Türkçe hata mesajıyla durur.
- Konteyner açılışta Alembic göçlerini çalıştırır, ardından seed verisini
  (kategoriler, ödeme yöntemleri, kullanıcılar) yalnızca eksikse ekler.
- Mini App varlıkları imaj derlenirken çok aşamalı `Dockerfile` içinde
  `node:20-alpine` katmanında üretilir ve çalışma katmanına kopyalanır; böylece
  Pi üzerinde Node çalıştırılmaz.
- **Mini App opsiyoneldir.** Telegram Mini App yalnızca geçerli sertifikaya
  sahip public HTTPS adreslerini kabul eder ve HA Ingress bu iş için
  kullanılamaz (Ingress, Telegram'ın istemcisinde bulunmayan HA oturum çerezini
  şart koşar). Bu nedenle Mini App, Ingress panelinin **yerine değil, yanına**
  eklenen ikinci bir giriş yoludur. Cloudflare Tunnel ile kurulumu
  `docs/DEPLOYMENT_HA.md` içinde adım adım anlatılacak, ancak sistem bu adım
  hiç yapılmadan da tam işlevsel olacaktır.

Geliştirme ortamı aynı imajı `docker-compose.yml` ile çalıştırır; tek fark
veritabanı yolu ve `ALLOW_DEV_AUTH=true` bayrağıdır (yalnızca yerelde,
`X-Dev-Telegram-User-Id` başlığı ile Mini App'i tarayıcıda denemek için).

---

## 6b. Hızlı metin girişi

Bota yazılan serbest metinle tek adımda harcama kaydı. Amaç, eller doluyken
veya arayüz açmaya değmeyecek küçük harcamalarda en kısa yolu sunmaktır.

**Dilbilgisi (deterministik, LLM yok):**

```
<tutar> [kategori] [açıklama...]
```

Örnekler:

| Girdi | Yorum |
|---|---|
| `500 market` | 500,00 TL, Market kategorisi, açıklama yok |
| `1.250,50 market Migros alışverişi` | tutar + kategori + açıklama |
| `85 yakıt` | 85,00 TL, Yakıt kategorisi |
| `320` | tutar var, kategori yok → bot kategori butonları sorar |

Kurallar:

- **Q1.** İlk belirteç tutar olarak ayrıştırılır (aynı `parse_amount_to_minor`
  fonksiyonu). Ayrıştırılamazsa metin harcama sayılmaz, arama olarak yorumlanır.
- **Q2.** İkinci belirteç aktif kategori adlarıyla büyük/küçük harf ve Türkçe
  karakter duyarsız karşılaştırılır. **Yalnızca tam veya tekil önek eşleşmesi**
  kabul edilir; birden fazla kategoriye uyuyorsa bot seçim butonları gösterir.
  Bulanık/benzerlik tahmini yapılmaz.
- **Q3.** Ödeme yöntemi metinden **tahmin edilmez**. Varsayılan `Nakit`'tir ve
  bot onay mesajında `💳 Kart seç` düğmesi sunar. Kart seçilirse taksit sorulur.
- **Q4.** Tarih varsayılan olarak bugündür (`Europe/Istanbul`).
- **Q5.** Kayıt her zaman aynı `services/expenses.py` fonksiyonundan geçer;
  hızlı giriş ayrı bir yazma yolu **açmaz**.
- **Q6.** Kayıttan sonra §18'deki standart onay mesajı, `✏️ Düzenle` ve
  `🗑 Sil` düğmeleriyle birlikte gönderilir.

Bu akış taksitli işlemler için tasarlanmamıştır; taksit gerekiyorsa bot
kullanıcıyı forma yönlendirir. Böylece hız uğruna finansal doğruluk bozulmaz.

---

## 7. Geliştirme aşamaları

Her aşamanın sonunda testler çalıştırılır ve çıktısı paylaşılır. Finans motoru
testleri kırmızıysa bir sonraki aşamaya geçilmez.

| # | Aşama | Çıktı | Geçiş kapısı |
|---|---|---|---|
| 1 | İskelet | Depo, bağımlılıklar, config, logging, `docker-compose` | `python -c "import app.main"` çalışır |
| 2 | Veri modeli | Modeller, Alembic ilk göçü, seed | Göç uygulanır, seed idempotent |
| 3 | Finans motoru | `money`, `dates`, `statement`, `installments` | §37'deki tüm birim testleri yeşil |
| 4 | Harcama servisi | Oluştur/güncelle/sil, audit, tek transaction | Yaşam döngüsü entegrasyon testleri yeşil |
| 5 | Raporlar | Aylık, ekstre, taksit, gelecek yük, kişi, arama | §40 rapor testi yeşil |
| 6 | API + kimlik | Uçlar, üç kimlik kaynağı, hata biçimi | Yetkisiz erişim testleri yeşil |
| 7 | Telegram botu | Ana menü, rapor ekranları, düzenle/sil onayı, hızlı metin girişi | Bot gerçek token ile elle çalıştırılıp doğrulanır |
| 8 | Web arayüzü | Form, önizleme, kaydetme, göreli yollar | Tarayıcıda uçtan uca kayıt |
| 9 | Dockerize | Çok aşamalı imaj, `aarch64` derlemesi | İmaj derlenir ve ayağa kalkar |
| 10 | HA add-on (Ingress) | `config.yaml` + `ingress: true`, `run.sh`, `DOCS.md` | Pi'de kurulur, panel açılır, kayıt yapılır |
| 11 | Yedekleme + CLI | `python -m app.cli backup`, retention | Yedek alınır, geri yükleme denenir |
| 12 | Dokümantasyon | README, DOCS, CHANGELOG, sorun giderme | Temiz kurulum belgeye bakılarak tekrarlanır |
| 13 | Mini App bağlama *(opsiyonel)* | Tünel kurulumu, `WEBAPP_PUBLIC_URL`, `initData` yolu | Telefonda Telegram içinden kayıt |

Aşama 13 sistemin çalışması için gerekli değildir; Aşama 10 tamamlandığında
sistem kullanıma hazırdır. Bu aşama, tünel kurmaya karar verdiğinde ayrıca
yapılır ve arayüz kodunda değişiklik gerektirmez.

Aşama 7 gerçek Telegram token'ı gerektirir. Token gelene kadar bu aşama sahte
bot arayüzüyle test edilir ve "doğrulanmadı" olarak raporlanır; çalıştığı
gözlenmeden tamamlandı denmez.

---

## 8. Riskler

| # | Risk | Etki | Önlem |
|---|---|---|---|
| R1 | Mini App public HTTPS adresi gerektirir; HA Ingress bunu karşılayamaz | **Azaltıldı** — artık bloke edici değil | Arayüz Ingress üzerinden altyapısız çalışır; Mini App opsiyonel Aşama 13'e taşındı; ayrıca bota hızlı metin girişi eklenir |
| R13 | Ingress yol öneki (`/api/hassio_ingress/<token>/`) mutlak yolları bozar | Arayüz açılmaz | Vite `base: './'`, tüm API çağrıları göreli; Ingress altında açılış testi |
| R14 | `X-Remote-User-Id` başlığının dışarıdan taklit edilmesi | Yetkisiz erişim | `ports` boş, uygulama yalnızca Supervisor ağından erişilebilir; başlık yalnızca Ingress kaynaklı isteklerde kabul edilir |
| R15 | HA kullanıcısının yerel kullanıcıya eşlenememesi | Panel açılır ama kayıt yapılamaz | `HA_USER_MAP` yapılandırması; eşleşme yoksa `403` ve anlaşılır Türkçe mesaj |
| R16 | Hızlı metin girişinin yanlış kategori/tutar tahmini | Yanlış kayıt | Bulanık eşleşme yok; belirsizlikte bot sorar; ödeme yöntemi tahmin edilmez; taksitli işlem forma yönlendirilir |
| R2 | Kart ayarı değişince geçmiş taksitlerin kayması | Finansal hata | Anlık görüntü sütunları + "kart ayarı değişikliği geçmişi etkilemez" testi |
| R3 | Harcama ve nakit akışının çift sayılması | Yanlış rapor | Ayrı uç adları, ayrı servis fonksiyonları, §40 kabul testi |
| R4 | Kuruş kaybı / yuvarlama | Toplam tutmaması | Tam sayı aritmetiği, `sum == total` değişmezi, özellik testi |
| R5 | Ay sonu ve artık yıl tarihleri | Yanlış ekstre tarihi | Merkezî `normalized_date`; 31/30/29 Şubat testleri |
| R6 | `due_day` ile `statement_day` eşitse ay kayması belirsizliği | Yanlış son ödeme | Kural, yapılandırılmış ham günler üzerinden karar verir (normalize edilmiş gün değil) ve belgelenir |
| R7 | Yarım yazılmış veri (expense var, taksit yok) | Veri bütünlüğü | Tek transaction + rollback testi |
| R8 | SQLite eşzamanlı yazma kilidi | İşlem hatası | WAL, `busy_timeout`, tek süreç, kısa transaction |
| R9 | Pi üzerinde imaj derleme süresi | Kurulum zorluğu | Çok aşamalı derleme, frontend'in Pi'de derlenmemesi |
| R10 | Token'ın loga veya depoya sızması | Güvenlik | Maskeleyen log filtresi, `.gitignore`, `.env.example` yer tutucu |
| R11 | Yumuşak silinmiş kaydın raporda görünmesi | Yanlış rapor | Filtre repository katmanında zorunlu, testle sabitlenir |
| R12 | Yerel saat farkı nedeniyle "bugün"ün kayması | Yanlış tarih | Tüm "bugün" hesapları `Europe/Istanbul` üzerinden tek yardımcıdan |

---

## 9. Kabul kriterleri

Aşağıdakilerin tamamı otomatik testle doğrulanır ve çıktısı paylaşılır.

**Finansal doğruluk**

1. `1000,00 TL / 3 taksit` → `[333,34; 333,33; 333,33]`, toplam tam olarak
   `100000` kuruş.
2. Şartname §38: kart `statement_day=10`, `due_day=20`; işlem `2026-09-08`,
   `3000 TL`, 3 taksit → ekstreler `2026-09-10`, `2026-10-10`, `2026-11-10`;
   son ödemeler `2026-09-20`, `2026-10-20`, `2026-11-20`; toplam `300000` kuruş.
3. Şartname §39: aynı kart, işlem `2026-09-11` → ekstreler `2026-10-10`,
   `2026-11-10`, `2026-12-10`; son ödemeler `2026-10-20`, `2026-11-20`,
   `2026-12-20`.
4. İşlem tarihi hesap kesim günüyle aynı: `cutoff_inclusive=true` → aynı ay;
   `cutoff_inclusive=false` → takip eden ay.
5. `statement_day=31`, Şubat 2027 → `2027-02-28`; Şubat 2028 → `2028-02-29`.
   `statement_day=30`, Şubat → ayın son günü.
6. `due_day > statement_day` → aynı ay; `due_day <= statement_day` → takip eden ay.
7. Aralık ekstresinin son ödemesi Ocak'a taşar; 12 taksitli işlem yıl sınırını
   doğru geçer.
8. Nakit ödemede `installment_count` 1'e zorlanır; 1'den büyük değer hata verir.

**Veri bütünlüğü**

9. Harcama oluşturma sırasında taksit yazımı hata alırsa hiçbir satır kalmaz.
10. Tutar, tarih, ödeme yöntemi veya taksit sayısı değişince plan yeniden
    üretilir; yalnızca açıklama veya kategori değişince plana dokunulmaz.
11. Kart ayarı değiştirildikten sonra eski harcamanın taksit tarihleri ve
    tutarları bit düzeyinde aynı kalır.
12. Yumuşak silinen harcama; aylık rapor, ekstre raporu, taksit raporu, gelecek
    yük raporu ve aramanın hiçbirinde görünmez.
13. Her oluşturma, güncelleme, silme ve geri alma işlemi için bir `audit_logs`
    satırı yazılır.

**Raporlama**

14. Şartname §40: Eylül'de 12.000 TL/12 taksit + 1.000 TL peşin + 500 TL nakit
    → aylık harcama raporu **13.500 TL**; aynı veri için ekstre bazlı Eylül
    yükü 12 taksitli işlemden yalnızca 1.000 TL içerir.
15. Gelecek yük raporu en az 12 ay üretir ve ekstre bazlı / son ödeme bazlı
    görünümleri ayrı ayrı verir.
16. Kişi bazlı rapor Aykut ve Aslıhan toplamlarını ayırır ve ikisinin toplamı
    aile toplamına eşittir.

**Güvenlik**

17. Yetkisiz Telegram kullanıcısı yalnızca `⛔ Bu botu kullanma yetkiniz
    bulunmuyor.` mesajını alır, başka hiçbir veri görmez.
18. Geçersiz imzalı, süresi geçmiş veya eksik `initData` ile yapılan API
    isteği `401`; geçerli imzalı ama yetkisiz kullanıcı `403` alır.
19. `HA_USER_MAP` içinde karşılığı olmayan bir `X-Remote-User-Id` `403` alır;
    hiçbir kimlik başlığı yokken istek `401` alır.
20. `created_by_user_id` istemciden gönderilerek değiştirilemez; hangi kimlik
    kaynağı kullanılırsa kullanılsın kayıt doğrulanmış kullanıcıya yazılır.
21. Log çıktısında bot token veya `initData` bulunmaz.

**Kullanılabilirlik ve dağıtım**

22. Arayüz Türkçe ve mobil önceliklidir; kredi kartı seçiliyken kaydetmeden
    önce taksit/ekstre önizlemesi gösterir. Aynı sayfa hem Ingress hem Mini App
    bağlamında çalışır; Telegram içinde açıldığında tema renklerine uyar.
23. Arayüz Ingress yol öneki altında sorunsuz açılır; hiçbir varlık veya API
    çağrısı mutlak yol kullanmaz.
24. `500 market` yazıldığında harcama kaydedilir; kategori belirsizse bot seçim
    sorar; tutar ayrıştırılamazsa kayıt oluşturulmaz.
25. Kayıt sonrası Telegram mesajı §18'deki alanları ve `✏️ Düzenle` / `🗑 Sil`
    butonlarını içerir; silme onay ister.
26. `python -m app.cli backup` `budget-YYYY-MM-DD-HHMMSS.db` üretir, SQLite'ın
    güvenli yedekleme API'sini kullanır ve retention ayarına uyar.
27. Add-on temiz bir HA OS kurulumunda yalnızca `DOCS.md` izlenerek, tünel veya
    alan adı kurmadan çalışır hale gelir.

---

## 10. Belgelenen varsayımlar

Finansal doğruluğu etkilemeyen, makul ve sonradan ayarlanabilir seçimler:

- **A1.** `public_id`, harcamanın birincil anahtarından `EXP-%06d` biçiminde
  türetilir; 999.999 kaydın üzerinde genişler.
- **A2.** MVP'de taksit durumu yalnızca `scheduled` olarak üretilir. `paid` ve
  `cancelled` değerleri şemada vardır ancak arayüzden işaretleme ileriye
  bırakılmıştır.
- **A3.** Herhangi bir taksiti `paid` işaretlenmiş harcamanın finansal alanları
  düzenlenemez; kullanıcıdan silip yeniden oluşturması istenir. MVP'de
  işaretleme olmadığı için pratikte tetiklenmez, ancak kural baştan konur.
- **A4.** *(1.3.0'da değişti — şartname §12'nin yerine geçer.)* Kullanıcı
  yalnızca hesap kesim gününü girer; son ödeme tarihi ekstre tarihinden
  `due_offset_days` (varsayılan 10) gün sonrası olarak hesaplanır ve **hafta
  sonuna denk gelirse pazartesiye taşınır**. Şartnamenin ilk hâlinde hafta sonu
  kaydırması yapılmaması yazıyordu; kullanıcı bunu açıkça tersine çevirdi.

  Bunun doğrudan sonucu olarak §38'deki kabul senaryosunun beklenen ilk son
  ödeme tarihi `2026-09-20` yerine `2026-09-21`'dir: 20 Eylül 2026 pazar
  gününe denk geliyor. Ekstre tarihleri değişmedi.

  Resmî tatiller hâlâ hesaba katılmaz; tatil takvimi yıldan yıla değiştiği için
  elde güvenilir bir kaynak olmadan tahmin yürütmek yanlış bir tarihi doğruymuş
  gibi göstermek olurdu. `expense_installments` şeması taksit bazında manuel
  tarih düzeltmesine uygun kalır.
- **A5.** Tek para birimi TRY'dir. `currency` sütunları şemada bulunur ancak
  MVP'de çoklu kur dönüşümü yapılmaz.
- **A6.** Aylık rapor ayları `Europe/Istanbul` yerel takvimine göre, ayın ilk
  gününden son gününe kapalı aralık olarak tanımlar.
- **A7.** Son kullanılan ödeme yöntemi/kategori hatırlama MVP'de yoktur; ancak
  `users` tablosuna sonradan tercih sütunları eklenebilecek şekilde bırakılır.
- **A8.** Bot mesajlarında tarih `2 Eylül 2026`, listelerde `02.09.2026`, para
  `12.450,75 TL` biçimindedir.
- **A9.** Hızlı metin girişinde ödeme yöntemi varsayılan `Nakit`'tir ve
  metinden tahmin edilmez; kart kullanımı onay mesajındaki düğmeyle seçilir.
- **A10.** HA kullanıcı kimliği ile yerel kullanıcı eşlemesi `HA_USER_MAP`
  yapılandırmasından gelir ve iki kullanıcılı bu kurulumda **zorunludur**;
  eşlemesi olmayan bir HA kullanıcısı `403` alır. Boş eşlemeyi varsayılan bir
  kullanıcıya bağlamak, kimin harcadığını belirsizleştireceği ve kişi bazlı
  raporu bozacağı için bilinçli olarak yapılmaz.

  Canlı Home Assistant örneğinden (2026-09-08) okunan gerçek kimlikler:

  | HA kullanıcısı | HA user id | Eşlendiği kişi |
  |---|---|---|
  | Aykut Cem | `70bbe879b6f145d9ba41e2ae8e2b81aa` | Aykut |
  | Aykut Tablet | `b85c0e5c28254c72975196463ef64217` | Aykut |
  | Aslıhan | `6ab54aa06b034eb6b80c7956c66fbf3b` | Aslıhan |
  | Kiosk Tablet | `bbb2e9efbf9441f8aa5173d3164495ff` | **eşlenmez** |

  Aykut'un iki HA kullanıcısı olduğu için ikisi de aynı kişiye eşlenir; aksi
  halde tabletten girilen harcamalar reddedilirdi. `Kiosk Tablet` bilinçli
  olarak eşlenmez: paylaşılan bir cihazda harcamayı kimin girdiği
  belirlenemeyeceği için kayıt oluşturulmasına izin verilmez. Aynı gerekçeyle
  `mqtt` ve `frigate_mqtt` servis kullanıcıları da eşlenmez.
