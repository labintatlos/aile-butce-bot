# Test Senaryoları

Şartname §37 ve §38–40'taki her madde burada izlenebilir bir kimlikle
listelenmiştir. Her senaryonun karşısında testin yazılacağı dosya bulunur.
Bu liste geliştirme sırasında kesme işareti olarak kullanılır: finans motoru
testleri (`U-*`) geçmeden üst katmanlara geçilmez.

## Birim testleri — para (`tests/unit/test_money.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| U-M1 | `1000,00 TL / 3 taksit` toplamı | `100000` kuruş, `[33334, 33333, 33333]` |
| U-M2 | `1 kuruş / 1 taksit` | `[1]` |
| U-M3 | 1–12 arası her taksit sayısı, rastgele 500 tutar | `sum == total` her zaman |
| U-M4 | `"1.250,50"`, `"1250,50"`, `"1250.50"`, `"₺1.250,50 TL"` | hepsi `125050` |
| U-M5 | `"0"`, `"-5"`, `""`, `"abc"` | `ValueError` |
| U-M6 | Yuvarlama `"10,005"` | `1001` (ROUND_HALF_UP) |
| U-M7 | `format_try(1245075)` | `"12.450,75 TL"` |
| U-M8 | Taksit sayısı 0 veya 13 | `ValueError` |

## Birim testleri — tarih (`tests/unit/test_dates.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| U-D1 | `statement_day=31`, Şubat 2027 | `2027-02-28` |
| U-D2 | `statement_day=31`, Şubat 2028 (artık yıl) | `2028-02-29` |
| U-D3 | `statement_day=30`, Şubat 2027 | `2027-02-28` |
| U-D4 | `add_months(2027-02-28, 1, tercih=31)` | `2027-03-31` |
| U-D5 | Aralık'tan Ocak'a geçiş, yıl artışı | doğru yıl |
| U-D6 | Gün `0` veya `32` | `ValueError` |

## Birim testleri — ekstre (`tests/unit/test_statement.py`)

| Kimlik | Senaryo (`statement_day=10`) | Beklenen ilk ekstre |
|---|---|---|
| U-S1 | işlem `2026-09-08` | `2026-09-10` |
| U-S2 | işlem `2026-09-10`, `cutoff_inclusive=true` | `2026-09-10` |
| U-S3 | işlem `2026-09-10`, `cutoff_inclusive=false` | `2026-10-10` |
| U-S4 | işlem `2026-09-11` | `2026-10-10` |
| U-S5 | işlem `2026-12-15` | `2027-01-10` |
| U-S6 | `due_day=20 > statement_day=10` | son ödeme aynı ay |
| U-S7 | `due_day=8 <= statement_day=28` | son ödeme takip eden ay |
| U-S8 | `due_day == statement_day` | son ödeme takip eden ay |
| U-S9 | `statement_day=25, due_day=5`, Aralık ekstresi | son ödeme Ocak |

## Birim testleri — taksit planı (`tests/unit/test_installments.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| U-I1 | 12 taksit, işlem Eylül 2026 | 12 ekstre, Ağustos 2027'ye kadar doğru ilerleyiş |
| U-I2 | 1 taksit (peşin) | tek satır, ilk ekstre = son ekstre |
| U-I3 | Nakit + `installment_count=3` | `ValueError` |
| U-I4 | Nakit + `installment_count=1` | tek satır, tarihler işlem tarihine eşit |
| U-I5 | Her planda `sum == total` | değişmez kural |
| U-I6 | Ekstre tarihleri kesin artan | doğrulanır |

## Birim testleri — hızlı metin girişi (`tests/unit/test_quick_entry.py`)

| Kimlik | Girdi | Beklenen |
|---|---|---|
| U-Q1 | `500 market` | `50000` kuruş, Market kategorisi, açıklama yok |
| U-Q2 | `1.250,50 market Migros alışverişi` | tutar `125050`, kategori Market, açıklama `Migros alışverişi` |
| U-Q3 | `320` | tutar var, kategori yok → kategori sorusu |
| U-Q4 | `merhaba` | Harcama değil; arama olarak yorumlanır |
| U-Q5 | `100 ye` (Yeme & İçme tekil önek) | Yeme & İçme eşleşir |
| U-Q6 | Birden fazla kategoriye uyan önek | Eşleşme yok, bot seçim sorar |
| U-Q7 | `100 MARKET` / `100 mArKeT` | Büyük-küçük harf ve Türkçe karakter duyarsız eşleşir |
| U-Q8 | Pasif kategori adı | Eşleşmez |
| U-Q9 | Ödeme yöntemi metinde geçse bile (`100 market nakit`) | Yöntem tahmin edilmez, `nakit` açıklamaya girer |

## Kabul testleri (`tests/acceptance/test_specification_cases.py`)

| Kimlik | Kaynak | Senaryo | Beklenen |
|---|---|---|---|
| A-1 | §38 | Kart 10/20, `2026-09-08`, 3000 TL, 3 taksit | Ekstreler `09-10`, `10-10`, `11-10`; son ödemeler `09-20`, `10-20`, `11-20`; toplam `300000` kuruş |
| A-2 | §39 | Aynı kart, `2026-09-11` | Ekstreler `10-10`, `11-10`, `12-10`; son ödemeler `10-20`, `11-20`, `12-20` |
| A-3 | §40 | Eylül: 12.000 TL/12 taksit + 1.000 TL peşin + 500 TL nakit | Aylık harcama raporu `13.500 TL` |
| A-4 | §40 | Aynı veri, ekstre bazlı Eylül yükü | Taksitli işlemden yalnızca 1.000 TL |

## Entegrasyon testleri — yaşam döngüsü (`tests/integration/test_expense_lifecycle.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| I-L1 | Harcama oluştur | expense + N taksit + audit satırı, tek commit |
| I-L2 | Taksit yazımı sırasında hata enjekte et | Hiçbir satır kalmaz (rollback) |
| I-L3 | Tutar güncelle | Plan yeniden üretilir, eski satırlar kalmaz |
| I-L4 | Tarih güncelle | Plan yeniden üretilir |
| I-L5 | Ödeme yöntemi güncelle | Plan ve anlık görüntü yenilenir |
| I-L6 | Taksit sayısı güncelle | Plan yeniden üretilir |
| I-L7 | Yalnızca kategori güncelle | Taksit satırları **değişmez** |
| I-L8 | Yalnızca açıklama güncelle | Taksit satırları **değişmez** |
| I-L9 | Kart `statement_day` değiştir, eski harcamayı oku | Taksit tarihleri ve tutarları aynı |
| I-L10 | Harcamayı sil | `deleted_at` dolar, satırlar durur, audit yazılır |
| I-L11 | `public_id` biçimi | `EXP-000001` deseni, tekil |
| I-L12 | Taksitlerden biri `paid` iken tutar düzenle | Reddedilir (Kural E4) |

## Entegrasyon testleri — raporlar (`tests/integration/test_reports.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| I-R1 | Aylık harcama raporu | Toplam, kişi kırılımı, kategori dağılımı, işlem sayısı, en yüksek harcama/kategori, nakit ve kart toplamları |
| I-R2 | Kişi toplamlarının toplamı | Aile toplamına eşit |
| I-R3 | Silinmiş harcama | Aylık, ekstre, taksit, gelecek yük ve aramanın hiçbirinde yok |
| I-R4 | Ekstre raporu | Kart bazında ilgili `statement_date` toplamı ve son ödeme tarihi |
| I-R5 | Aktif taksit raporu | `4/12`, kalan borç ve aylık ortalama doğru |
| I-R6 | Tüm taksitleri `paid`/`cancelled` olan harcama | Aktif taksit listesinde yok |
| I-R7 | Gelecek yük raporu | En az 12 ay; ekstre bazlı ve son ödeme bazlı ayrı ayrı |
| I-R8 | Arama | Büyük/küçük harf duyarsız, Türkçe karakterli; tarih/tutar/kategori/yöntem/kullanıcı filtreleri ve sayfalama |
| I-R9 | `%` ve `_` içeren arama metni | Joker olarak yorumlanmaz |

## Entegrasyon testleri — güvenlik (`tests/integration/test_authorization.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
2.0.0 ile Telegram botu ve Mini App kaldırıldı; I-S1, I-S2, I-S5, I-S6, I-S9 ve
I-S13 onlara aitti ve emekliye ayrıldı. Şifreyle girişin senaryoları
`tests/integration/test_web_login.py` içindedir.

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| I-S3 | Hiçbir kimlik bilgisi yok | `401` |
| I-S4 | Eski `Authorization: tma ...` başlığı gönderilir | `401`, yanıtta başlık içeriği yok |
| I-S7 | Pasif kullanıcı (`is_active=false`) | `403` |
| I-S8 | Gövdede `created_by_user_id` gönderilir | Yok sayılır, doğrulanmış kimlik kullanılır |
| I-S10 | Ingress isteği, `HA_USER_MAP` içinde eşlenmiş `X-Remote-User-Id` | Doğru kullanıcıya bağlanır |
| I-S11 | Ingress isteği, eşlenmemiş ve kayıtlı olmayan kimlik | `403` |
| I-S12 | İnternete açık örnekte uydurma `X-Remote-User-Id` | Kabul edilmez, `401` |
| I-S14 | Aynı kişi sitede şifreyle ve HA panelinden kayıt yapar | İkisi de aynı `users` satırına yazılır |

## Yedekleme testleri (`tests/integration/test_backup.py`)

| Kimlik | Senaryo | Beklenen |
|---|---|---|
| I-B1 | `python -m app.cli backup` | `budget-YYYY-MM-DD-HHMMSS.db` üretilir |
| I-B2 | Yedek açılır ve sorgulanır | Kayıt sayıları kaynakla aynı |
| I-B3 | Retention `3` iken 5 yedek | En eski 2 yedek silinir |
