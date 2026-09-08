# Aile Bütçe Takip — Kurulum

Bu eklenti, Telegram üzerinden aile bütçesi ve kredi kartı taksit takibi
sağlar. Harcama girişi hem Home Assistant panelinden hem de Telegram
üzerinden yapılabilir.

---

## 1. Telegram botunu oluştur

1. Telegram'da **@BotFather**'a yaz.
2. `/newbot` komutunu gönder.
3. Bota bir ad ver (örneğin `Aile Bütçe`).
4. Bir kullanıcı adı ver; `bot` ile bitmeli (örneğin `aile_butce_bot`).
5. BotFather sana bir **token** verir. Bu token bir paroladır: kimseyle
   paylaşma, ekran görüntüsüne alma.

## 2. Telegram kullanıcı kimliklerini öğren

Bot yalnızca izin verdiğin kişilerce kullanılabilir. Kimlikleri öğrenmek için:

1. Telegram'da **@userinfobot**'a yaz.
2. `/start` gönder; sana kendi sayısal kimliğini söyler.
3. Aynısını eşinin telefonunda da yapın.

Not: Bu kimlikler `123456789` gibi sayılardır, kullanıcı adı değildir.

## 3. Eklentiyi kur

1. Home Assistant'ta **Ayarlar → Eklentiler → Eklenti Mağazası**'nı aç.
2. Sağ üstteki **⋮** menüsünden **Depolar**'ı seç.
3. Şu adresi ekle:

   ```
   https://github.com/labintatlos/aile-butce-bot
   ```

4. Sayfayı yenile; **Aile Bütçe Takip** eklentisi listede görünür.
5. Eklentiye tıkla ve **Kur** de. İlk kurulum arayüzün derlenmesini de
   içerdiği için birkaç dakika sürebilir.

## 4. Ayarları gir

Eklentinin **Yapılandırma** sekmesinde:

| Alan | Ne yazılır |
|---|---|
| `telegram_bot_token` | BotFather'dan aldığın token |
| `authorized_telegram_ids` | İki kimlik, virgülle: `111111111,222222222` |
| `user_display_names` | `111111111:Aykut,222222222:Aslıhan` |
| `ha_user_map` | Home Assistant kimliği eşlemesi (aşağıya bak) |
| `webapp_public_url` | Şimdilik **boş bırak** |
| `timezone` | `Europe/Istanbul` |
| `backup_retention` | Kaç yedek saklanacak (varsayılan 14) |

**Kaydet**, sonra **Başlat**.

### `ha_user_map` nedir

Harcamayı kimin girdiğinin doğru kaydedilmesi için Home Assistant
kullanıcılarını Telegram kimlikleriyle eşleştirmek gerekir. Eşlemesi olmayan
bir Home Assistant kullanıcısı arayüzü açamaz — bu bilinçlidir: paylaşılan bir
tablet hesabından girilen harcamanın kime ait olduğu belirlenemez ve kişi
bazlı rapor sessizce yanlışlanırdı.

Home Assistant kullanıcı kimliğini bulmak için **Geliştirici Araçları →
Şablon** bölümüne şunu yapıştır:

```jinja
{% for state in states.person %}
{{ state.name }} = {{ state.attributes.user_id }}
{% endfor %}
```

Çıkan kimlikleri şu biçimde yaz:

```
70bbe879...:111111111,6ab54aa0...:222222222
```

Bir kişinin birden fazla Home Assistant hesabı varsa (örneğin kendi hesabı ve
bir tablet hesabı) **ikisini de aynı Telegram kimliğine** eşle.

## 5. Kullanmaya başla

- **Home Assistant paneli:** Sol menüde **Bütçe** görünür. Harcama formu
  buradan açılır; ek bir kurulum gerekmez.
- **Telegram:** Bota `/start` yaz. Menüden raporlara ulaşabilir, ya da
  doğrudan `500 market` gibi yazarak hızlı kayıt yapabilirsin.

## 6. Kredi kartlarını ayarla

Eklenti üç örnek kart ile başlar ve bunların hesap kesim / son ödeme günleri
**bilinçli olarak yer tutucudur** (1 ve 15). Gerçek değerleri girmeden taksit
tarihleri anlamlı olmaz.

Botta **⚙️ Ayarlar** yaz; kartlar numaralarıyla listelenir. Sonra:

| Komut | Ne yapar |
|---|---|
| `/kartgun 2 26` | 2 numaralı kartın hesap kesim gününü 26 yapar |
| `/kartekle Aykut Kredi Kartı 2 \| 26` | Yeni kart ekler (ad ile gün `\|` ile ayrılır) |
| `/kartad 3 Yeni Kart Adı` | Kartın adını değiştirir |
| `/kartsil 3` | Kartı siler |
| `/kartpasif 3` · `/kartaktif 3` | Kartı gizler / geri açar |

Girilecek tek şey **hesap kesim günü**: ekstrenin kesildiği ayın günü.
Bankanın uygulamasında "hesap kesim tarihi" olarak geçer.

**Son ödeme tarihini girmezsin, sistem hesaplar.** Ekstre kesildikten 10 gün
sonrasıdır ve o gün hafta sonuna denk gelirse pazartesiye taşınır.

Örnek: hesap kesim günü 26 olan bir kartla 8 Eylül'de 3.000 TL / 3 taksit
harcama yaparsan taksitler 26 Eylül, 26 Ekim ve 26 Kasım ekstrelerine düşer;
son ödemeleri sırasıyla 6 Ekim, 5 Kasım ve 7 Aralık olur (6 Aralık pazara
denk geldiği için pazartesiye kaymıştır).

Bankan 10 günden farklı çalışıyorsa vadeyi de yazabilirsin:
`/kartgun 2 26 vade 12`

Kategoriler için `/kategori` yaz; aynı mantıkla `/kategoriekle 🎬 Sinema`,
`/kategoriad`, `/kategorisil`, `/kategoripasif` ve `/kategoriaktif` çalışır.

### Silme hakkında bilinmesi gereken

Bir kart veya kategori **hiçbir harcamada kullanılmıyorsa** gerçekten silinir.
Kullanılıyorsa silinmez; bot bunun yerine pasife almayı önerir. Sebebi şu:
kaydı silmek, ona bağlı geçmiş harcamaların ödeme yöntemini veya kategorisini
okunamaz hâle getirir ve eski raporlar bozulur. Pasife alınan bir kart yeni
harcamalarda görünmez ama geçmiş raporlarda yerinde kalır.

Kart adını değiştirmek de geçmişi bozmaz: her harcama kaydedildiği andaki kart
adını kendi içinde saklar.

---

## Telegram Mini App (isteğe bağlı)

Formu Home Assistant yerine doğrudan Telegram içinden açmak istersen, dışarıya
açık ve **geçerli sertifikaya sahip HTTPS** bir adres gerekir. Home Assistant
Ingress bu iş için kullanılamaz; Telegram'ın istemcisinde Home Assistant oturum
çerezi bulunmaz.

Keenetic modemin varsa **KeenDNS** bunu ücretsiz sağlar. Adımlar
`docs/DEPLOYMENT_HA.md` dosyasındadır.

Adres hazır olduğunda `webapp_public_url` alanına yaz ve eklentiyi yeniden
başlat. Bu adres girilene kadar sistem tam işlevlidir; yalnızca Telegram
içinden form açma özelliği kapalı kalır.

---

## Yedekleme

Veritabanı `/data/budget.db` altındadır ve Home Assistant'ın kendi eklenti
yedeklerine dahildir.

Elle yedek almak için eklentinin terminalinde:

```bash
python -m app.cli backup
```

Yedekler `/data/backups/` altında `budget-2026-09-02-230000.db` biçiminde
saklanır. `backup_retention` ayarından fazlası otomatik silinir.

Yedekleme, çalışan veritabanını kopyalamak yerine SQLite'ın kendi güvenli
yedekleme mekanizmasını kullanır; eklenti çalışırken de tutarlı bir yedek
üretir.

---

## Sorun giderme

**Bot yanıt vermiyor.**
Eklenti günlüğüne bak. `Telegram bot token yapılandırılmamış` yazıyorsa token
alanı boştur. Token doğruysa ve bot hâlâ sessizse, Telegram kimliğinin
`authorized_telegram_ids` içinde olduğundan emin ol.

**Bot "⛔ Bu botu kullanma yetkiniz bulunmuyor" diyor.**
Telegram kimliğin listede değil. @userinfobot ile kimliğini doğrula ve
ayarlara ekle, sonra eklentiyi yeniden başlat.

**Panel açılıyor ama "Bu uygulamayı kullanma yetkiniz bulunmuyor" diyor.**
Home Assistant kullanıcın `ha_user_map` içinde eşlenmemiş. Yukarıdaki şablonla
kimliğini bul ve ekle.

**Eklenti başlamıyor, günlükte göç hatası var.**
Veritabanı göçü başarısız olmuştur ve eklenti bilerek başlatılmamıştır;
verilerine dokunulmamıştır. Günlüğü paylaş.

**Eklenti sürekli yeniden başlıyor, Supervisor günlüğü sadece "exit code 1" diyor.**
Supervisor günlüğü eklentinin kendi çıktısını göstermez. Eklentinin sayfasındaki
**Günlük** sekmesine bak; gerçek hata orada yazar. Açılışta bir yapılandırma
denetimi çalışır ve hatalı alanın adını söyler (örneğin
`'user_display_names' ayarındaki 'Aykut' girdisi hatalı`).

**Günlükte "Telegram bot token geçersiz" yazıyor.**
Token yanlış veya eksik girilmiş. BotFather'dan aldığın değeri
`telegram_bot_token` alanına yapıştır ve eklentiyi yeniden başlat. Bu durumda
bot çalışmaz ama Home Assistant panelindeki form çalışmaya devam eder.

**Taksit tarihleri yanlış görünüyor.**
Kartın hesap kesim ve son ödeme günlerini kontrol et. Kurulumdaki yer tutucu
değerler (1 ve 15) düzeltilmemiş olabilir. Kart ayarını değiştirmek **geçmiş
harcamaların taksit planını değiştirmez** — bu bilinçlidir; yeni ayar yalnızca
sonraki harcamalara uygulanır.

**Aylık harcama toplamı kart borcumdan yüksek.**
Bu doğrudur ve iki farklı şeydir. Aylık rapor, o ay yapılan harcamaların **tam
tutarını** gösterir: 12 taksitli 12.000 TL'lik bir alışveriş o ayın raporunda
12.000 TL olarak görünür. Kart yükü ise yalnızca o aya düşen taksiti sayar.
İkisini toplama.
