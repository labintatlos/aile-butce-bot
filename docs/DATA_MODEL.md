# Veri Modeli

Tüm para alanları `INTEGER` ve **kuruş** cinsindedir. Tüm tarihler `DATE`
(saat bilgisi yok), tüm zaman damgaları UTC `DATETIME`'dır; gösterim
`Europe/Istanbul` saatine çevrilerek yapılır.

## ER şeması

```
+---------------------+
| users               |
+---------------------+
| id            PK    |
| telegram_user_id  U |
| ha_user_id      U ? |
| display_name        |
| role                |
| is_active           |
| created_at          |
| updated_at          |
+----+-----------+----+
     |           |
     |           | owner_user_id
     |           v
     |     +----------------------------+
     |     | payment_methods            |
     |     +----------------------------+
     |     | id                    PK   |
     |     | name                   U   |
     |     | type  (cash|credit_card)   |
     |     | owner_user_id         FK   |
     |     | currency                   |
     |     | statement_day     NULL     |
     |     | due_day           NULL     |
     |     | credit_limit_minor NULL    |
     |     | cutoff_inclusive           |
     |     | notes             NULL     |
     |     | is_active                  |
     |     | created_at / updated_at    |
     |     +-------------+--------------+
     |                   |
     | created_by_user_id| payment_method_id
     v                   v
+----------------------------------------+        +--------------------+
| expenses                               |        | categories         |
+----------------------------------------+        +--------------------+
| id                              PK     |        | id            PK   |
| public_id                        U     |        | name           U   |
| created_by_user_id              FK     |        | emoji              |
| payment_method_id               FK     |<-------| is_active          |
| category_id                     FK     |        | sort_order         |
| transaction_date                       |        | created_at         |
| total_amount_minor                     |        +--------------------+
| currency                               |
| installment_count                      |
| description                     NULL   |
| statement_day_snapshot          NULL   |
| due_day_snapshot                NULL   |
| cutoff_inclusive_snapshot       NULL   |
| payment_method_type_snapshot           |
| payment_method_name_snapshot           |
| created_at / updated_at                |
| deleted_at                      NULL   |
+---------------------+------------------+
                      |
                      | expense_id  (ON DELETE CASCADE)
                      v
        +--------------------------------+
        | expense_installments           |
        +--------------------------------+
        | id                        PK   |
        | expense_id                FK   |
        | installment_number             |
        | installment_count              |
        | amount_minor                   |
        | statement_date                 |
        | due_date                       |
        | status (scheduled|paid|cancelled)
        | created_at                     |
        | UNIQUE(expense_id, installment_number)
        +--------------------------------+

+--------------------------------+
| audit_logs                     |
+--------------------------------+
| id                        PK   |
| user_id                   FK?  |
| entity_type                    |
| entity_id                      |
| action (create|update|delete|restore)
| old_data                  NULL |  JSON metni
| new_data                  NULL |  JSON metni
| created_at                     |
+--------------------------------+
```

## Tablo sözleşmeleri

### users

| Sütun | Tip | Kural |
|---|---|---|
| `id` | INTEGER PK | |
| `telegram_user_id` | INTEGER | UNIQUE, NOT NULL |
| `ha_user_id` | TEXT NULL | UNIQUE; Home Assistant Ingress kullanıcı kimliği |
| `display_name` | TEXT | NOT NULL (`Aykut`, `Aslıhan`) |
| `role` | TEXT | `owner` \| `member` |
| `is_active` | BOOLEAN | NOT NULL, varsayılan 1 |

Seed: `AUTHORIZED_TELEGRAM_IDS` ve `USER_DISPLAY_NAMES` yapılandırmasından
üretilir. ID'ler koda gömülmez.

`ha_user_id`, arayüz Home Assistant Ingress üzerinden açıldığında gelen
`X-Remote-User-Id` başlığıyla eşleşir ve `HA_USER_MAP` yapılandırmasından
doldurulur. Böylece aynı kişi hem Telegram hem HA üzerinden giriş yaptığında
harcamalar tek bir kullanıcıya yazılır. Eşleşme bulunamazsa istek `403` alır;
kayıt asla belirsiz bir kullanıcıya yazılmaz.

### payment_methods

| Sütun | Tip | Kural |
|---|---|---|
| `type` | TEXT | `cash` \| `credit_card` |
| `statement_day` | INTEGER NULL | `credit_card` için 1–31 zorunlu |
| `due_day` | INTEGER NULL | `credit_card` için 1–31 zorunlu |
| `cutoff_inclusive` | BOOLEAN | `credit_card` için NOT NULL, varsayılan 1 |
| `credit_limit_minor` | INTEGER NULL | opsiyonel |
| `owner_user_id` | INTEGER NULL | nakit için NULL olabilir |

Veritabanı düzeyinde CHECK kısıtları:

```
CHECK (type IN ('cash','credit_card'))
CHECK (type <> 'cash' OR (statement_day IS NULL AND due_day IS NULL))
CHECK (type <> 'credit_card' OR (statement_day BETWEEN 1 AND 31
                             AND due_day       BETWEEN 1 AND 31))
```

Seed: `Nakit`, `Aslıhan Kredi Kartı 1`, `Aslıhan Kredi Kartı 2`,
`Aykut Kredi Kartı 1`. Bunlar yalnızca başlangıç satırıdır; kod hiçbir yerde
bu isimlere veya id'lere göre dallanmaz. Kart eklenebilir, düzenlenebilir ve
pasife alınabilir; silinmez (geçmiş harcamalar bağlı kalır).

### categories

Seed (sıralı): Market, Yeme & İçme, Araç, Yakıt, Ev, Faturalar, Alışveriş,
Giyim, Sağlık, Eğitim, Eğlence, Seyahat, Hediye, Çocuk, Evcil Hayvan, Diğer.
Her biri bir emoji taşır. Kategoriler pasife alınabilir, silinmez.

### expenses

| Sütun | Kural |
|---|---|
| `public_id` | `EXP-%06d`, UNIQUE, kullanıcıya gösterilen kimlik |
| `total_amount_minor` | `CHECK (> 0)` |
| `installment_count` | `CHECK (BETWEEN 1 AND 12)` |
| `transaction_date` | NOT NULL |
| `deleted_at` | NULL ise aktif |

Anlık görüntü (snapshot) sütunları harcama oluşturulurken ödeme yönteminden
kopyalanır ve **bir daha güncellenmez**; yalnızca harcamanın finansal alanları
düzenlenip plan yeniden üretilirse o anki kart değerleriyle yeniden yazılır.
Bu sayede kart ayarı sonradan değiştiğinde geçmiş planlar sabit kalır.

Nakit için `statement_day_snapshot` ve `due_day_snapshot` NULL, `installment_count`
1'dir; bu kural hem serviste hem CHECK kısıtıyla korunur.

### expense_installments

Bir harcamanın taksitleri, harcama ile **aynı transaction** içinde yazılır.
Değişmez kural:

```
SUM(expense_installments.amount_minor WHERE expense_id = X)
    == expenses.total_amount_minor WHERE id = X
```

İndeksler: `expense_id`, `statement_date`, `due_date`, `status`.

`statement_date` ve `due_date` doğrudan saklanır (yeniden hesaplanmaz); bu,
ileride taksit bazında manuel tarih düzeltmesi eklemeyi de mümkün kılar.

### audit_logs

`old_data` ve `new_data`, ilgili kaydın JSON serileştirilmiş halidir. Para
alanları kuruş olarak yazılır. Bu tabloya bot token'ı, `initData` veya başka
kimlik doğrulama verisi asla yazılmaz.

## SQLite yapılandırması

Bağlantı açılışında uygulanan PRAGMA'lar:

```
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

Veritabanı yolu `DATABASE_PATH` ortam değişkeninden gelir; Home Assistant
kurulumunda varsayılan `/data/budget.db`.
