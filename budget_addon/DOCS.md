# Aile Bütçe Takip — Kurulum

Bu eklenti aile bütçesi ve kredi kartı taksit takibi için bir web sitesi
çalıştırır. Site telefondan ve bilgisayardan kullanıcı adı ve şifreyle açılır;
aynı arayüz Home Assistant'ın sol menüsünde de görünür.

Home Assistant yalnızca sunucuyu çalıştıran makinedir. İnternetten erişim için
Keenetic modemin KeenDNS hizmeti kullanılır (bkz. `docs/DEPLOYMENT_HA.md`).

---

## 1. Eklentiyi kur

1. Home Assistant'ta **Ayarlar → Eklentiler → Eklenti Mağazası**'nı aç.
2. Sağ üstteki **⋮** menüsünden **Depolar**'ı seç.
3. Şu adresi ekle:

   ```
   https://github.com/labintatlos/aile-butce-bot
   ```

4. Sayfayı yenile; **Aile Bütçe Takip** eklentisi listede görünür.
5. Eklentiye tıkla ve **Kur** de. İlk kurulum arayüzün derlenmesini de
   içerdiği için birkaç dakika sürebilir.
6. **Başlat**'a bas. Hiçbir ayarı doldurmak zorunlu değildir.

## 2. Yönetici hesabını oluştur

1. Eklentinin **Günlük** sekmesini aç. Şuna benzer bir satır görürsün:

   ```
   İlk yönetici henüz oluşturulmadı. Siteyi açın ve şu kurulum kodunu girin: 1234-5678
   ```

2. Ev ağından siteyi aç: `http://homeassistant.local:8100` (açılmazsa
   Raspberry Pi'nin IP adresini yaz, örneğin `http://192.168.1.50:8100`).
3. **İlk kurulum** ekranında kodu gir, adını, kullanıcı adını ve şifreni yaz.

Kod her yeniden başlatmada günlüğe tekrar yazılır ve yönetici oluşturulduktan
sonra geçersiz olur.

## 3. Diğer kişileri ekle

**Kişiler** ekranında (yalnızca yöneticiler görür) **Kişi ekle**'ye bas:

- **İsim** raporlarda görünen addır.
- **Kullanıcı adı** 3-32 karakter; küçük harf, rakam, nokta, alt çizgi veya
  tire.
- **Şifre** en az 8 karakter.
- **Yönetici** kişi başkalarını ekleyip şifre sıfırlayabilir.
- **Siteye girebilir** kapatılırsa kişi silinmez, geçmiş kayıtları durur ama
  giriş yapamaz; açık oturumları hemen kapanır.

Herkes kendi şifresini **Ayarlar → Hesap → Şifre değiştir**'den değiştirebilir.
Şifre değişince o kişinin diğer cihazlardaki oturumları kapanır.

## 4. Kredi kartlarını ayarla

Eklenti Nakit ve üç örnek kartla başlar. Kartların hesap kesim günü
**bilinçli olarak yer tutucudur**; gerçek değeri girmeden taksit tarihleri
anlamlı olmaz.

**Ayarlar → Ödeme yöntemleri** bölümünde kartı aç ve düzenle:

| Alan | Ne yazılır |
|---|---|
| Hesap kesim günü | Ekstrenin kesildiği ayın günü; bankanın uygulamasında "hesap kesim tarihi" |
| Son ödeme | Kesimden kaç gün sonra (genellikle 10) |
| Kredi limiti | İsteğe bağlı; doluysa limitin %90'ı bağlanınca uyarı gelir |
| Sahibi | Kartın kime ait olduğu |

**Son ödeme tarihini gün olarak girmezsin, sistem hesaplar.** Ekstre
kesildikten sonraki gün sayısı eklenir; o gün hafta sonuna denk gelirse
pazartesiye taşınır.

Örnek: hesap kesim günü 26 olan bir kartla 8 Eylül'de 3.000 TL / 3 taksit
harcama yaparsan taksitler 26 Eylül, 26 Ekim ve 26 Kasım ekstrelerine düşer;
son ödemeleri sırasıyla 6 Ekim, 5 Kasım ve 7 Aralık olur (6 Aralık pazara
denk geldiği için pazartesiye kaymıştır).

Kategoriler aynı ekranın **Kategoriler** bölümündedir; simge, ad ve isteğe
bağlı aylık bütçe hedefi girilir.

### Silme hakkında bilinmesi gereken

Bir kart veya kategori **hiçbir harcamada kullanılmıyorsa** gerçekten silinir.
Kullanılıyorsa silinmez; bunun yerine **Aktif** işaretini kaldırarak gizlenir.
Kaydı silmek, ona bağlı geçmiş harcamaların ödeme yöntemini veya kategorisini
okunamaz hâle getirir ve eski raporlar bozulurdu. Pasif kart yeni harcamalarda
görünmez ama geçmiş raporlarda yerinde kalır.

Kart adını değiştirmek de geçmişi bozmaz: her harcama kaydedildiği andaki kart
adını kendi içinde saklar.

## 5. İnternetten eriş

Ev dışından açmak için 8100 portunu **HTTPS** veren bir adrese yayınla.
Keenetic modem için adımlar `docs/DEPLOYMENT_HA.md` içindedir. Adres hazır
olunca eklenti ayarlarında `site_url` alanına yaz (örneğin
`https://butce.evim.keenetic.pro`) ve eklentiyi yeniden başlat.

Modemde 8100 portunu doğrudan düz HTTP olarak internete açma: şifre
şifrelenmeden gider.

## 6. Bildirimler

Ekstre kesimi, yaklaşan son ödeme, haftalık ve aylık özet, bütçe ve kart
limiti uyarıları her gün `reminder_hour` saatinde hazırlanır ve sitenin
**Bildirimler** ekranına düşer. Her kişi **Ayarlar → Bildirimler**'den:

- hatırlatmaları kendisi için kapatabilir,
- **Bu cihazda anlık bildirim**'i açabilir (telefon kilitliyken de gelir;
  site HTTPS adresinden açılmış olmalıdır),
- e-posta adresini yazıp **E-postayla da gönder**'i açabilir.

E-posta seçeneği yalnızca `smtp_host` ve `smtp_sender` doluysa görünür. Gmail
için:

| Alan | Değer |
|---|---|
| `smtp_host` | `smtp.gmail.com` |
| `smtp_port` | `587` |
| `smtp_security` | `starttls` |
| `smtp_username` | Gmail adresin |
| `smtp_password` | Google hesabında oluşturulan **uygulama şifresi** (normal şifre çalışmaz) |
| `smtp_sender` | `Aile Bütçe <adresin@gmail.com>` |

Ayarlardaki **Deneme gönder** düğmesi e-postanın ve anlık bildirimin gerçekten
ulaştığını hemen gösterir.

## 7. Home Assistant paneli

Sol menüdeki **Bütçe** aynı siteyi Home Assistant oturumunla, şifre sormadan
açar. Harcamayı kimin girdiğinin doğru kaydedilmesi için Home Assistant
kullanıcısını sitedeki kişiyle eşleştirmek gerekir. Eşlemesi olmayan bir Home
Assistant kullanıcısı paneli açamaz — bu bilinçlidir: paylaşılan bir tablet
hesabından girilen harcamanın kime ait olduğu belirlenemezdi.

Home Assistant kullanıcı kimliğini bulmak için **Geliştirici Araçları →
Şablon** bölümüne şunu yapıştır:

```jinja
{% for state in states.person %}
{{ state.name }} = {{ state.attributes.user_id }}
{% endfor %}
```

`ha_user_map` alanına kimlik ve sitedeki kullanıcı adını yaz:

```
70bbe879...:aykut,6ab54aa0...:aslihan
```

2.0 öncesinden kalan `70bbe879...:111111111` biçimindeki değerler de çalışmaya
devam eder.

---

## Ayarlar

| Alan | Ne işe yarar |
|---|---|
| `site_url` | Sitenin internet adresi; bildirim bağlantıları ve anlık bildirim için |
| `ha_user_map` | Home Assistant paneli eşlemesi (bölüm 7) |
| `timezone` | `Europe/Istanbul` |
| `backup_retention` | Kaç yedek saklanacak (varsayılan 14) |
| `enable_reminders` | Günlük hatırlatmaları tümüyle kapatır |
| `reminder_hour` | Hatırlatmaların hazırlandığı saat (0-23) |
| `due_reminder_days` | Son ödemeden kaç gün önce uyarılsın |
| `smtp_*` | E-posta bildirimleri (bölüm 6) |
| `publish_ha_sensors` | Bütçe değerlerini Home Assistant sensörlerine yazar |

## Güvenlik

- Şifre veritabanına düz metin olarak değil, yalnızca özet olarak yazılır.
- **Beni hatırla** işaretliyse oturum 30 gün, değilse tarayıcı kapanana kadar
  (en fazla 12 saat) açık kalır.
- Aynı adresten 15 dakika içinde 10 hatalı deneme yapılırsa giriş 15 dakika
  durdurulur. Doğru şifreyle giren kişi hiçbir zaman yavaşlatılmaz. Site
  KeenDNS üzerinden açıldığında bütün internet istekleri modemden geliyormuş
  gibi görünür; biri dışarıdan art arda yanlış şifre denerse ev dışından giriş
  15 dakika bekletilebilir. Ev ağından giriş etkilenmez.
- Fiş fotoğrafları `/data/receipts/` altında tahmin edilemeyen adlarla
  saklanır ve yalnızca giriş yapmış kişilere gösterilir.

---

## Yedekleme

Veritabanı `/data/budget.db`, fiş fotoğrafları `/data/receipts/` altındadır ve
ikisi de Home Assistant'ın kendi eklenti yedeklerine dahildir.

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

**Kurulum kodunu bulamıyorum.**
Eklentiyi yeniden başlat; kod günlüğe tekrar yazılır. Günlükte kod yoksa
yönetici zaten oluşturulmuştur, giriş ekranını kullan.

**Şifremi unuttum.**
Başka bir yönetici **Kişiler** ekranından yeni şifre verebilir. Tek yönetici
sensen ve şifreni unuttuysan günlükteki hataları paylaş.

**Panel açılıyor ama "Bu uygulamayı kullanma yetkiniz yok" diyor.**
Home Assistant kullanıcın `ha_user_map` içinde eşlenmemiş. Bölüm 7'deki
şablonla kimliğini bul ve ekle.

**Anlık bildirim seçeneği çalışmıyor.**
Tarayıcılar anlık bildirime yalnızca HTTPS adreslerde izin verir. Siteyi
`http://...:8100` yerine KeenDNS adresinden aç ve `site_url` alanının dolu
olduğundan emin ol. iPhone'da önce siteyi **Ana Ekrana Ekle** ile uygulama
gibi kurmak gerekir.

**Eklenti başlamıyor, günlükte göç hatası var.**
Veritabanı göçü başarısız olmuştur ve eklenti bilerek başlatılmamıştır;
verilerine dokunulmamıştır. Günlüğü paylaş.

**Eklenti sürekli yeniden başlıyor, Supervisor günlüğü sadece "exit code 1" diyor.**
Supervisor günlüğü eklentinin kendi çıktısını göstermez. Eklentinin sayfasındaki
**Günlük** sekmesine bak; gerçek hata orada yazar. Açılışta bir yapılandırma
denetimi çalışır ve hatalı alanın adını söyler (örneğin
`'ha_user_map' ayarındaki 'aykut' girdisi hatalı`).

**Günlükte "table _alembic_tmp_... already exists" yazıyor.**
Daha önceki bir açılışta veritabanı göçü yarıda kesilmiş ve geriye geçici bir
tablo kalmış demektir. Eklenti bunu açılışta kendisi temizler; yeniden
başlatmak yeterlidir. Günlükte "Yarım kalmış göçten kalan ... siliniyor"
satırını görürsün.

**Taksit tarihleri yanlış görünüyor.**
Kartın hesap kesim gününü ve son ödeme gün sayısını kontrol et. Kurulumdaki
yer tutucu değer düzeltilmemiş olabilir. Kart ayarını değiştirmek **geçmiş
harcamaların taksit planını değiştirmez** — bu bilinçlidir; yeni ayar yalnızca
sonraki harcamalara uygulanır.

**Aylık harcama toplamı kart borcumdan yüksek.**
Bu doğrudur ve iki farklı şeydir. Aylık rapor, o ay yapılan harcamaların **tam
tutarını** gösterir: 12 taksitli 12.000 TL'lik bir alışveriş o ayın raporunda
12.000 TL olarak görünür. Kart yükü ise yalnızca o aya düşen taksiti sayar.
İkisini toplama.
