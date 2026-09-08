# Değişiklik Günlüğü

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
