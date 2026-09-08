# Finansal Hesaplama Kuralları

Bu doküman sistemin tek finansal doğruluk kaynağıdır. Buradaki her kural
`backend/app/services/finance/` altında saf (yan etkisiz) fonksiyonlarla
uygulanır ve `backend/tests/` altında testle sabitlenir. Hiçbir hesaplamada
yapay zekâ, tahmin veya kayan noktalı sayı kullanılmaz.

---

## 1. Para

**Kural P1.** Para veritabanında `INTEGER` ve kuruş cinsinden tutulur.
`12.345,67 TL` → `1234567`.

**Kural P2.** Kullanıcı girdisi `Decimal` ile ayrıştırılır, iki basamağa
`ROUND_HALF_UP` ile yuvarlanır, sonra kuruşa çevrilir. `float` hiçbir aşamada
kullanılmaz.

Kabul edilen girdi biçimleri: `1250`, `1250,50`, `1.250,50`, `1250.50`,
`1.250,50 TL`, `₺1.250,50`. Binlik ayracı `.`, ondalık ayracı `,` kabul edilir;
yalnızca `.` içeren ve tek noktalı girdi ondalık olarak yorumlanır.

**Kural P3.** Tutar sıfırdan büyük olmalıdır. `0` ve negatif değerler reddedilir.

**Kural P4.** Gösterim biçimi `12.450,75 TL`'dir.

---

## 2. Taksit tutarının dağıtılması

**Kural T1 (kayıpsızlık).** Taksitlerin toplamı harcama toplamına birebir eşit
olmak zorundadır:

```
sum(installments.amount_minor) == expense.total_amount_minor
```

**Kural T2 (algoritma).**

```python
base, remainder = divmod(total_amount_minor, installment_count)
amounts = [base + (1 if i < remainder else 0) for i in range(installment_count)]
```

Fazla kuruşlar **ilk** taksitlere eklenir.

Örnek: `1000,00 TL / 3` → `100000` kuruş → `base=33333, remainder=1` →
`[33334, 33333, 33333]` → `333,34 + 333,33 + 333,33 = 1000,00 TL`.

**Kural T3.** `installment_count` 1 ile 12 arasındadır. `1` = peşin.

**Kural T4.** Ödeme yöntemi `cash` ise `installment_count` zorunlu olarak `1`'dir.
Arayüz taksit seçimini devre dışı bırakır, sunucu 1'den farklı bir değeri
reddeder.

---

## 3. Tarih normalizasyonu

**Kural D1.** Bir ayda bulunmayan gün, o ayın son gününe indirilir.

```
normalized_date(y, m, gun) = date(y, m, min(gun, ayin_son_gunu(y, m)))
```

Örnekler: gün 31 → Şubat 2027'de `2027-02-28`; Şubat 2028'de (artık yıl)
`2028-02-29`; Nisan'da `2026-04-30`.

**Kural D2.** Ay ekleme her zaman **tercih edilen gün** (kartın yapılandırılmış
`statement_day` / `due_day` değeri) korunarak yapılır; bir önceki ayda normalize
edilmiş gün bir sonraki aya taşınmaz.

```
add_months(2027-02-28, 1, tercih=31) = 2027-03-31     (2027-03-28 DEĞİL)
```

Bu kural, 31'lik bir kartın Şubat'tan sonra 28'e sabitlenmesini engeller.

**Kural D3.** Aynı normalizasyon hem ekstre hem son ödeme tarihine uygulanır.

---

## 4. İlk ekstre tarihi (hesap kesim)

**Kural S1.**

```
aday = normalized_date(islem_yili, islem_ayi, statement_day)

ilk_ekstre =
    aday                              , eger islem_tarihi <  aday
    aday                              , eger islem_tarihi == aday ve cutoff_inclusive
    add_months(aday, 1, statement_day), aksi halde
```

**Kural S2.** `cutoff_inclusive` kart bazında ayarlanır. Varsayılan `true`:
hesap kesim günündeki harcama aynı ayın ekstresine girer. `false` yapılırsa o
günkü harcama takip eden ekstreye kayar.

Örnekler (`statement_day = 10`):

| İşlem tarihi | `cutoff_inclusive` | İlk ekstre |
|---|---|---|
| 2026-09-08 | true | 2026-09-10 |
| 2026-09-10 | true | 2026-09-10 |
| 2026-09-10 | false | 2026-10-10 |
| 2026-09-11 | true | 2026-10-10 |

---

## 5. Sonraki ekstreler

**Kural S3.** İlk ekstreden sonraki her taksit tam bir ay ilerler:

```
ekstre_n = add_months(ilk_ekstre, n - 1, statement_day)
```

---

## 6. Son ödeme tarihi

Kullanıcı **yalnızca hesap kesim gününü** girer. Son ödeme tarihi bundan
türetilir; ayrıca bir gün girilmez.

**Kural S4.**

```
son_odeme_n = is_gunune_kaydir(ekstre_n + due_offset_days gun)
```

`due_offset_days` varsayılan olarak **10**'dur. Türkiye'de yaygın uygulama
budur, ancak bankadan bankaya değiştiği için kart bazında ayarlanabilir
tutulur: yanlış bir gün sayısı, sistemin hata vermeden her ay yanlış son ödeme
tarihi üretmesine yol açardı.

Ay sonu normalizasyonuna burada gerek yoktur; gün eklemek takvimi doğrudan
takip eder ve `31 Ocak + 10 gün` gibi bir durumda ayın var olmayan gününe
düşme sorunu oluşmaz.

**Kural S5 (hafta sonu kaydırması).** Hesaplanan son ödeme tarihi cumartesi
veya pazara denk gelirse **pazartesiye** taşınır, çünkü bankalar hafta sonu
tahsilat yapmaz.

```
cumartesi -> +2 gun
pazar     -> +1 gun
```

**Resmî tatiller hesaba katılmaz.** Tatil takvimi yıldan yıla değişir; elde
güvenilir bir kaynak olmadan tahmin yürütmek, yanlış bir tarihi doğruymuş gibi
göstermek olurdu.

Örnekler (`due_offset_days = 10`):

| Ekstre | +10 gün | Gün | Son ödeme |
|---|---|---|---|
| 2026-09-10 | 2026-09-20 | Pazar | **2026-09-21** |
| 2026-10-10 | 2026-10-20 | Salı | 2026-10-20 |
| 2026-09-02 | 2026-09-12 | Cumartesi | **2026-09-14** |
| 2027-01-31 | 2027-02-10 | Çarşamba | 2027-02-10 |

`statement_date` ve `due_date` hesaplanan değil **saklanan** alanlardır;
ileride taksit bazında manuel tarih düzeltmesi eklenebilir.

---

## 7. Nakit harcamalar

**Kural C1.** Nakit harcamada ekstre kavramı yoktur. Tek taksit üretilir,
`statement_date` ve `due_date` işlem tarihine eşitlenir. Böylece nakit akışı
raporları nakit harcamayı işlem gününde gösterir ve kredi kartı yüküyle
karışmaz (rapor sorguları ödeme yöntemi tipine göre ayrılabilir).

---

## 8. Harcama ve nakit akışı ayrımı

Bu ayrım sistemin en kritik raporlama kuralıdır ve iki toplam **asla**
birbirine eklenmez.

**Kural R1 (spending).** Aylık harcama raporu `expenses.total_amount_minor`
değerini `transaction_date` ayına yazar. Taksit sayısı bu raporu etkilemez.

**Kural R2 (cash flow).** Ekstre ve gelecek yük raporları
`expense_installments.amount_minor` değerlerini `statement_date` veya
`due_date` ayına göre toplar.

Örnek: 5 Eylül'de 12.000 TL / 12 taksit televizyon.

| Rapor | Eylül değeri |
|---|---|
| Aylık harcama | 12.000 TL |
| Ekstre bazlı yük | 1.000 TL |
| Son ödeme bazlı yük | 1.000 TL (kartın son ödeme ayına göre) |

**Kural R3.** Arayüz nakit akışı raporlarında hangi perspektifin kullanıldığını
açıkça yazar: **"Ekstre Bazlı"** veya **"Son Ödeme Bazlı"**.

**Kural R4.** Yumuşak silinmiş (`deleted_at IS NOT NULL`) harcamalar ve onların
taksitleri hiçbir finansal raporda görünmez.

---

## 9. Düzenleme sonrası yeniden hesaplama

**Kural E1.** Aşağıdaki alanlardan biri değişirse taksit planı tamamen yeniden
üretilir ve kart anlık görüntüsü o anki değerlerle yenilenir:

- `total_amount_minor`
- `transaction_date`
- `payment_method_id`
- `installment_count`

**Kural E2.** Yalnızca `description` veya `category_id` değişirse taksit planına
**dokunulmaz**.

**Kural E3.** Yeniden üretme tek transaction içinde yapılır: eski taksitler
silinir, yenileri yazılır, denetim kaydı eklenir; herhangi bir adım başarısız
olursa tamamı geri alınır.

**Kural E4.** Bir harcamanın herhangi bir taksiti `paid` durumundaysa finansal
alanları düzenlenemez; kullanıcıdan kaydı silip yeniden oluşturması istenir.

**Kural E5.** Kart ayarlarının (hesap kesim/son ödeme günü, `cutoff_inclusive`)
sonradan değiştirilmesi mevcut hiçbir harcamanın taksit planını değiştirmez.
Değişiklik yalnızca o andan sonra oluşturulan harcamalara uygulanır.

---

## 10. Doğrulanacak değişmez kurallar

Bu ifadeler testlerde doğrudan kontrol edilir:

1. `sum(installments) == expense.total` — her harcama için, her zaman.
2. `len(installments) == expense.installment_count`.
3. Taksit numaraları `1..n` aralığında ve tekildir.
4. `installment[n].statement_date` kesin olarak artan sıradadır.
5. `installment[n].due_date >= installment[n].statement_date`.
6. Nakit harcamada `installment_count == 1`.
7. Aylık harcama toplamı, o ayın silinmemiş harcamalarının `total_amount_minor`
   toplamına eşittir.
8. Kişi bazlı toplamların toplamı aile toplamına eşittir.
9. Bir harcama silindiğinde tüm raporlardaki katkısı tam olarak sıfırlanır.
10. Kart ayarı değiştikten sonra eski taksit satırları bit düzeyinde aynıdır.
