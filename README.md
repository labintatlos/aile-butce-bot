# Aile Bütçe Takip

Aykut ve Aslıhan'ın harcamalarını Telegram üzerinden hızlıca kaydettiği, kredi
kartı taksitlerini ve ekstre yükünü otomatik hesaplayan aile bütçe takip
sistemi. Raspberry Pi 5 üzerinde Home Assistant OS altında bir add-on olarak
çalışır.

> **Durum:** Geliştirme aşamasında. Tasarım tamamlandı, uygulama sürüyor.
> Ayrıntılar için [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Ne yapar

- Harcamaları kişi, kategori, ödeme yöntemi ve tarihe göre kaydeder.
- Kredi kartı taksitlerini otomatik oluşturur.
- Kartın hesap kesim ve son ödeme günlerine göre her taksitin hangi ekstreye
  düşeceğini hesaplar.
- Aylık harcama, ekstre, aktif taksit ve gelecek 12 aylık ödeme yükü raporları
  üretir.
- Yalnızca yetkilendirilmiş iki Telegram kullanıcısı tarafından kullanılabilir.

## Temel ilkeler

- **Finansal hesaplamalarda yapay zekâ kullanılmaz.** Tutar, tarih, taksit,
  ekstre ve rapor hesaplarının tamamı deterministik Python koduyla yapılır.
- **Para `float` ile tutulmaz.** Tüm tutarlar tam sayı ve kuruş cinsindendir.
- **Kuruş kaybı olmaz.** Taksitlerin toplamı her zaman harcama toplamına eşittir.
- **Geçmiş yeniden hesaplanmaz.** Kart ayarları değişse bile oluşturulmuş
  taksit planları sabit kalır.

## Belgeler

| Belge | İçerik |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Mimari, aşamalar, riskler, kabul kriterleri |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | ER şeması ve tablo sözleşmeleri |
| [docs/FINANCE_RULES.md](docs/FINANCE_RULES.md) | Taksit ve ekstre hesaplama kuralları |
| [docs/TEST_SCENARIOS.md](docs/TEST_SCENARIOS.md) | Test senaryolarının izlenebilir listesi |

## Güvenlik notu

Bu depo **public**'tir, çünkü Home Assistant özel add-on depolarını kimlik
doğrulaması yapmadan klonlar. Bu nedenle depoda hiçbir gerçek sır bulunmaz:
Telegram bot token'ı, yetkili kullanıcı kimlikleri ve genel adres yalnızca
Home Assistant add-on ayarlarında saklanır.

## Kurulum

Home Assistant OS kurulum adımları add-on paketlendiğinde
`docs/DEPLOYMENT_HA.md` içinde yayımlanacaktır.
