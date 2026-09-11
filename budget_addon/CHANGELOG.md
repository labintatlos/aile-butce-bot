# Değişiklik Günlüğü

## 2.1.2

**"Ortak" yanlış anlaşılmıştı; denkleştirme kaldırıldı.** "Ortak" burada
evin ortak (hane) gideri anlamına geliyor, iki kişi arasında bölüşülüp
kimin kime borçlu olduğu hesaplanacak bir masraf paylaşımı değil. Bu yanlış
varsayımla eklenmiş "Ortak gider denkleştirmesi" özelliği — kim ne kadar
ödedi, kimin kime ne kadar borcu var hesaplaması, hem özet hem raporlar
sayfasındaki kartı, API uç noktası, backend servisi ve ilgili testler dahil
— tamamen kaldırıldı. Harcama eklerken "Ortak" / "kişisel" ayrımı olduğu
gibi kalıyor: kişisel işaretlenen harcama sahibinin yıllık kişisel
bütçesinden düşmeye devam ediyor, sadece artık "denkleştirme" diye bir
kavramdan söz edilmiyor.

Verified with `budget_addon/backend` pytest (503 passed) and `npm run build`
(tsc --noEmit + vite build, hatasız).

## 2.1.1

Görsel/arayüz cilası: sayfa değişiminde içerik yumuşak yükselerek belirir
(her ziyarette yeniden oluşan bir sarmalayıcı üzerinden), ikincil/hayalet
düğmelerde masaüstünde ince bir hover gölgesi eklendi. Bildirim ve pencere
animasyonları zaten vardı. Su Ürünleri ve Görev Maliyet siteleriyle aynı
hareket eğrisi kullanılır; üçü arasında ortak bir görsel dil kuruldu.
`npm run build` (tsc + vite, hatasız) ve `.smoke-ui.py` ile telefon/masaüstü,
açık/koyu temada doğrulandı.

## 2.1.0

**Kişisel yıllık bütçeler.** Harcama eklerken artık "Ortak", "Aykut kişisel"
veya "Aslıhan kişisel" seçilebiliyor. Kişisel harcama, kimin kartıyla
alındığına ve kaydı kimin girdiğine bakılmaksızın sahibinin yıllık kişisel
bütçesinden düşer ve ortak gider denkleştirmesine girmez. Taksitli kişisel
alışverişin tamamı alışveriş tarihinde bütçeden düşer; iadeler geri eklenir.

Özet ekranındaki "Kişisel bütçeler" kartında her kişinin yıllık bütçesi,
harcadığı ve kalan tutar, yılın ne kadarının geçtiğiyle birlikte görünür;
bütçeler aynı karttan düzenlenir. Bütçe her yıl sıfırlanır. Raporlarda aylık
harcama Tümü / Ortak / kişi bazında süzülebilir. Daha önce kişisel işaretlenen
harcamalar, kaydı giren kişiye ait sayılır.

## 2.0.5

Son ödeme tarihi geçen taksit artık kendiliğinden ödenmiş sayılıyor. Kart
limiti her ay ödenen taksit kadar geri açılıyor; önceden limit hiç
boşalmadığı için kartlar zamanla dolu görünür ve gereksiz limit uyarısı
gelirdi. Taksit listesinde "kalan" tutarı ve harcama detayındaki "Ödendi"
etiketi de buna göre gösteriliyor. Raporlar ve ayın nakit çıkışı
değişmedi.

## 2.0.4

Kredi kartı son ödeme tarihi artık resmî tatilleri de atlıyor: hafta sonuna
veya bayrama (dinî bayramlar dahil) denk gelirse ilk iş gününe taşınır.
Arifeler iş günü sayılır. Daha önce kaydedilmiş, günü gelmemiş taksitlerin
tarihleri de güncelleme sırasında düzeltilir.

## 2.0.3

Chrome sayfayı İngilizce sanıp otomatik çevirdiğinde menü ve metinler
bozuluyordu ("Onlar" gibi). Site artık tarayıcı çevirisine kapalı.

## 2.0.2

Arayüz metinleri daha doğal bir Türkçeyle yeniden yazıldı; site adı her yerde
"Aile Bütçesi" oldu. Bildirim ayarlarında hatırlatma saati artık doğru
gösteriliyor.

## 2.0.1

Arayüz daha ferah kartlar, zümrüt yeşili görsel tema ve yenilenmiş giriş
ekranıyla geliştirildi. Özet ekranında gelir, toplam çıkış ve kalan bütçe daha
kolay karşılaştırılıyor; gelirler, sabit giderler ve raporlar için hızlı işlem
bağlantıları eklendi. Mobil gezinme, koyu tema ve klavye erişimi de iyileştirildi.

## 2.0.0

Telegram botu ve Telegram Mini App kaldırıldı. Sistem artık yalnızca
kullanıcı adı ve şifreyle açılan bir web sitesi; aynı arayüz Home Assistant
panelinde de açılmaya devam ediyor. Botta olup sitede olmayan her şey
kaldırılmadan önce siteye taşındı:

**Kişiler sitede yönetiliyor.** İlk açılışta günlükte bir kurulum kodu
yazıyor; siteye bu kodla girilip yönetici hesabı oluşturuluyor. Diğer kişiler,
şifre sıfırlama, yönetici yetkisi ve siteye giriş izni **Kişiler** ekranında.
Herkes kendi şifresini **Ayarlar**'dan değiştirebiliyor.

**Hatırlatmalar sitede, e-postada ve anlık bildirim olarak.** Ekstre kesimi,
yaklaşan son ödeme, bütçe ve kart limiti uyarıları sitenin **Bildirimler**
ekranına düşüyor; isteyen e-postayla veya telefonda anlık bildirim olarak da
alıyor. E-posta için eklenti ayarlarına `smtp_*` alanları eklendi.

**Fiş fotoğrafı ve hızlı giriş.** Fiş fotoğrafı sitede harcamaya yükleniyor ve
eklentinin veri klasöründe saklanıyor. "500 market" gibi hızlı giriş sitede
de botla aynı kurallarla çalışıyor.

**Ayarlar sadeleşti.** `telegram_bot_token`, `authorized_telegram_ids`,
`user_display_names`, `web_users` ve `webapp_public_url` kaldırıldı; hiçbir
ayar zorunlu değil. Sitenin internet adresi yeni `site_url` alanına yazılıyor.
`ha_user_map` artık `ha_kimliği:kullanıcı_adı` biçiminde; eski
`ha_kimliği:telegram_kimliği` değerleri de tanınıyor. Web sitesi portu (8100)
varsayılan olarak açık.

**Güncellemeden önce:** 1.5.0'da **Kişiler** ekranında herkesin kullanıcı
adı ve şifresi olduğundan emin olun. Güncellemeden sonra `site_url` alanına
KeenDNS adresinizi yazın (bkz. `docs/DEPLOYMENT_HA.md`).

Telegram döneminde bota gönderilmiş fiş fotoğrafları eklentide değil
Telegram'da durur; sitede görünmez, Telegram sohbetinde kalmaya devam eder.
Veritabanındaki eski Telegram kimlik sütunları veri kaybı olmasın diye
silinmedi, yalnızca kullanılmıyor.

Yönetici olmayan bir kişi **Kişiler** adresini elle açarsa artık özet ekranına
yönlendiriliyor.

## 1.5.0

Bu sürümle sistem tam bir web sitesine dönüşüyor. Telegram botu ve Home
Assistant paneli olduğu gibi çalışmaya devam ediyor; web sitesi aynı
veritabanını ve aynı hesap kurallarını kullanıyor.

**Kullanıcı adı ve şifreyle giriş.** `web_users` ayarına
`telegram_id:kullanici_adi:sifre` yazılan kişi web sitesine girebiliyor. Şifre
veritabanına yalnızca scrypt özeti olarak yazılıyor; oturum imzalı ve
JavaScript'in okuyamadığı bir çerezde duruyor. Şifre değiştirildiğinde veya kişi
listeden çıkarıldığında açık oturumlar kendiliğinden kapanıyor. Aynı adresten 15
dakikada 10 hatalı denemeden sonra giriş geçici olarak durduruluyor; doğru
şifreyle giren hiçbir zaman yavaşlatılmıyor.

**Botta ne varsa sitede de var.** Özet ekranı, taksit ve ekstre önizlemeli
harcama girişi, aranabilir ve filtrelenebilir harcama listesi, harcama
düzenleme ve silme, iadeler, gelirler, sabit giderler, aylık / kart / yıllık
raporlar, bütçe hedefleri, kart limitleri, etiketler, ortak gider
denkleştirmesi, CSV dışa aktarma (ay veya bütün yıl), kart ve kategori
ayarları, hatırlatıcıyı açıp kapama.

**Telefon ve bilgisayar.** Geniş ekranda kenar çubuklu masaüstü düzeni, telefonda
alt gezinme çubuğu. Açık ve koyu tema cihaz ayarını izliyor; Telegram içinde
Telegram'ın renkleri kullanılıyor.

**Yayın.** Web sitesi 8100 portundaki genel sunucudan sunuluyor. Bu sunucu artık
`web_users` veya `webapp_public_url` doluysa başlıyor ve Ingress başlığına
güvenmiyor.

Fiş fotoğrafları Telegram'da kalıyor; sitede yalnızca "fiş eklendi" işareti
görünüyor.

## 1.4.0

Bu sürüm sistemi bir harcama defterinden bütçe yöneticisine çeviriyor. Taksit
ve ekstre hesabına dokunulmadı; hepsi mevcut motorun üzerine eklendi.

**Sistem artık sorulmadan da konuşuyor.** Her gün belirlenen saatte ekstre
kesim günü, yaklaşan son ödeme, haftalık ve aylık kapanış özetleri geliyor.
Gönderilen her bildirim veritabanında işaretleniyor; eklenti gün içinde on kez
yeniden başlasa da aynı bildirim iki kez gelmiyor. `/hatirlatici` ile kapatılıp
açılabiliyor.

**Sabit giderler.** Kira, aidat, abonelik bir kez tanımlanıyor ve her ay günü
geldiğinde kendiliğinden kaydediliyor. Kayıt tarihi şablonun günü oluyor:
eklenti üç gün kapalı kalsa bile kira ayın 1'ine yazılıyor. Komutlar: `/sabit`,
`/sabitekle`, `/sabittutar`, `/sabitgun`, `/sabitpasif`, `/sabitsil`.

**Kategori bütçe hedefleri.** Bir kategoriye aylık hedef konabiliyor; hedefin
%80'ine gelindiğinde ve hedef aşıldığında haber veriliyor. Hedef bir sınır
değil: hiçbir kayıt bu yüzden engellenmiyor. `/butce`, `/butceayarla`.

**Gelir kaydı ve "ay sonunda ne kalıyor".** Gelir girildiğinde 💰 Durum ekranı
ayın nakit tablosunu çıkarıyor: 12 taksitli bir alışverişin yalnızca bu aya
düşen taksiti, nakit harcamalar ve günü henüz gelmemiş sabit giderler.
`/gelir`, `/gelirler`.

**Home Assistant sensörleri.** Eklenti artık HA'ya altı sensör yazıyor: bu ay
harcama, gelir, ay sonunda kalan, yaklaşan ekstre, bütçesi aşılan kategori
sayısı ve kart borcu. Panoya kart konabiliyor, otomasyon yazılabiliyor.

**Kart limiti.** Kartın bağlı limiti, kullanılabilir bakiyesi ve %90'da uyarı.
`/kartlar`, `/kartlimit`.

**İadeler.** Ürün iade edildiğinde harcama silinmiyor; iade ayrı bir alacak
olarak kaydediliyor ve aylık rapor, kategori bütçesi, kart limiti, ekstre
toplamı ile nakit çıkışından düşülüyor. Kısmi iade destekleniyor. `/iade`.

**Fiş fotoğrafı.** Bota gönderilen fotoğraf harcamaya iliştiriliyor.
Açıklamasında tutar varsa yeni kayıt açıyor, yoksa son harcamaya ekleniyor.
Tutar fotoğraftan okunmuyor.

**Etiketler.** Açıklamaya `#bodrum` yazınca farklı kategorilerdeki harcamalar
tek toplamda birleşiyor. `/etiket`.

**Ay sonu tahmini, yıllık karşılaştırma ve CSV dışa aktarma.** `/tahmin`,
`/yil`, `/disaaktar`.

**Ortak / kişisel ayrımı ve denkleştirme.** Harcamalar varsayılan olarak ortak;
`#kisisel` yazılan ayrı tutuluyor. `/denklestir` kimin kime ne kadar borçlu
olduğunu kuruş kaybı olmadan söylüyor.

**Mini App'te rapor ekranı.** Panelde ikinci bir sekme: ayın durumu, kategori
dağılımı, bütçe hedefleri, kart limitleri, denkleştirme ve 12 aylık sütun
grafiği.

## 1.3.4

- Göçün "FOREIGN KEY constraint failed" ile düşmesi giderildi. Ödeme yöntemleri
  tablosu yeniden oluşturulurken eskisi siliniyor; harcamalar tablosu bu tabloya
  referans verdiği için yabancı anahtar zorlaması silme işlemini engelliyordu.
  Zorlama artık yalnızca göç süresince kapatılıyor, göç bitince veri bir kez
  denetlenip tekrar açılıyor.
- Göçleri gerçek bir veritabanı üzerinde uçtan uca çalıştıran testler eklendi;
  bu hata sınıfı yayınlanmadan önce yakalanabilecek.

## 1.3.3

- Yarım kalmış bir veritabanı göçünden otomatik kurtarma eklendi. Eklenti
  önceki sürümlerde döngüye girdiğinde göç yarıda kesilip geride geçici bir
  tablo bırakıyor, sonraki her açılış bu yüzden düşüyordu.
- Göç adımları koşullu hâle getirildi; yarım uygulanmış bir şemada kaldığı
  yerden tamamlanabiliyor.

## 1.3.2

- Eklentinin açılışta çökmesine yol açan ikinci hata giderildi: Home Assistant
  ayarlarında boş bırakılan isteğe bağlı alanlar uygulamaya `null` metni olarak
  geliyordu ve yapılandırma okuyucusu bunu geçersiz girdi sayıyordu.
- Açılışta yapılandırma denetimi eklendi; hatalı bir ayar artık hangi alanın
  bozuk olduğunu söyleyen anlaşılır bir mesaj veriyor.
- Geçersiz bot token'ı artık günlüğe açıkça yazılıyor ve arayüzü durdurmuyor.

## 1.3.1

- Eklentinin açılışta çökmesine yol açan hata giderildi: bir göç, tabloyu
  yeniden oluştururken zaman damgası sütununun varsayılanını taşımıyordu.

## 1.3.0

- Son ödeme tarihi artık kullanıcı tarafından girilmez; hesap kesim gününden
  hesaplanır (varsayılan 10 gün sonrası).
- Son ödeme tarihi hafta sonuna denk gelirse pazartesiye taşınır.
- Kart eklerken ve düzenlerken yalnızca hesap kesim günü sorulur.

## 1.2.0

- Kart ekleme, silme, ad değiştirme, hesap kesim ve son ödeme günü düzenleme.
- Kategori ekleme, silme, ad ve emoji düzenleme.
- Kullanımdaki bir kart veya kategori silinmez; pasife alma önerilir, böylece
  geçmiş raporlar okunabilir kalır.

## 1.1.0

- Harcama arama, analiz ekranı ve ayarlar ekranı bota eklendi.
- Kayıt mesajındaki düzenle düğmesi kategori değiştirmeyi açar.

## 1.0.0

İlk sürüm.

- Telegram üzerinden harcama kaydı: form ve `500 market` biçiminde hızlı metin girişi.
- Kredi kartı taksitlerinin ve ekstre tarihlerinin deterministik hesaplanması.
- Aylık harcama, ekstre, aktif taksit ve 12 aylık ödeme yükü raporları.
- Arayüz Home Assistant panelinden (Ingress) ve isteğe bağlı olarak Telegram
  Mini App üzerinden kullanılabilir.
- SQLite'ın güvenli yedekleme mekanizmasıyla yedek alma ve saklama kuralı.
