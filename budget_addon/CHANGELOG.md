# Değişiklik Günlüğü

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
