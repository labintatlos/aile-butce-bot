# Aile Bütçe Takip

Aykut ve Aslıhan'ın harcamalarını web sitesinden ve Telegram üzerinden
kaydettiği, kredi kartı taksitlerini ve ekstre yükünü otomatik hesaplayan aile
bütçe takip sistemi. Raspberry Pi 5 üzerinde Home Assistant OS altında bir
add-on olarak çalışır.

> **Durum:** Backend, bot, web sitesi ve eklenti paketlemesi tamamlandı; test
> paketi (544 test) yeşil. Gerçek Telegram token'ı ve Raspberry Pi üzerinde
> uçtan uca doğrulama bekliyor. Ayrıntılar için
> [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), sürüm notları için
> [CHANGELOG.md](budget_addon/CHANGELOG.md).

## Ne yapar

**Kayıt**

- Harcamaları kişi, kategori, ödeme yöntemi ve tarihe göre kaydeder.
- Kredi kartı taksitlerini otomatik oluşturur ve kartın hesap kesim ile son
  ödeme günlerine göre her taksitin hangi ekstreye düşeceğini hesaplar.
- Gelirleri kaydeder, iadeleri harcamayı silmeden düşer (kısmi iade dâhil).
- Kira, aidat, abonelik gibi sabit giderleri her ay kendiliğinden kaydeder.
- Fiş fotoğrafını harcamaya iliştirir.

**Kendiliğinden haber verir**

- Ekstre kesim günü, yaklaşan son ödeme, haftalık ve aylık kapanış özeti.
- Kategori bütçe hedefi aşılmak üzereyken ve aşıldığında.
- Kart limitinin %90'ı bağlandığında.

**Raporlar**

- Aylık harcama, ekstre, aktif taksit ve gelecek 12 aylık ödeme yükü.
- Ay sonunda ne kalacağı, ay sonu harcama tahmini, geçen yılla karşılaştırma.
- Kategori hedefleri, kart limitleri, etiket toplamları.
- Ortak giderlerde kimin kime ne kadar borçlu olduğu.
- CSV dışa aktarma; Home Assistant'a altı sensör.

**Erişim**

- **Web sitesi:** kullanıcı adı ve şifreyle; telefon ve bilgisayar uyumlu.
  Botta ne varsa sitede de var.
- **Telegram botu** ve **Home Assistant paneli** aynı veriyle çalışmaya devam
  eder.
- Yalnızca yetkilendirilmiş kişiler kullanabilir; şifreler yalnızca özet
  olarak saklanır.

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

Home Assistant'ta **Ayarlar → Eklentiler → Eklenti Mağazası → ⋮ → Depolar**
bölümüne bu deponun adresini ekle, ardından **Aile Bütçe Takip** eklentisini
kur.

Adım adım anlatım: [budget_addon/DOCS.md](budget_addon/DOCS.md)

Arayüz Home Assistant panelinden ek bir kurulum olmadan çalışır. Formu
doğrudan Telegram içinden açmak istersen (isteğe bağlı) public bir HTTPS
adresi gerekir; Keenetic KeenDNS ile kurulumu
[docs/DEPLOYMENT_HA.md](docs/DEPLOYMENT_HA.md) içinde anlatılmıştır.

## Geliştirme

```bash
cd budget_addon/backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest

cd ../frontend
npm install && npm run build
```
