# Home Assistant OS Dağıtımı

Sistem iki farklı giriş noktası sunar ve bunlar birbirinin alternatifidir:

| Giriş | Kimlik | Altyapı gereksinimi | Kurulum zorluğu |
|---|---|---|---|
| **Home Assistant paneli (Ingress)** | HA oturumu | **yok** | eklentiyi kur, bitti |
| **Telegram Mini App** | imzalı `initData` | public HTTPS adres | KeenDNS veya tünel |

Ingress ilk günden çalışır. Mini App isteğe bağlıdır ve sistemin çalışması için
gerekli değildir.

Eklentinin kurulumu ve ayarları `budget_addon/DOCS.md` içindedir. Bu belge
yalnızca isteğe bağlı Mini App adımını anlatır.

---

## Neden Ingress Mini App için kullanılamaz

Home Assistant Ingress, add-on arayüzünü HA'nın kendi HTTPS'i ve kendi oturumu
üzerinden sunar. Tarayıcıda çalışır çünkü HA oturum çerezin vardır.

Telegram Mini App'i açan gömülü tarayıcıda o çerez **yoktur**. Ingress adresi
Telegram içinde açıldığında kimlik doğrulamada takılır. Bu yüzden Mini App
istiyorsan, uygulamaya doğrudan ulaşan ayrı bir public adres gerekir.

Sistem bu ayrımı iki ayrı süreçle çözer:

```
                Home Assistant Supervisor agi
                            |
                     port 8099 (Ingress)
                     X-Remote-User-Id'ye GUVENIR
                     Telegram botunu bu surec calistirir
                            |
                     [ ayni kod, ayni veritabani ]
                            |
                     port 8100 (genel)
                     Basliga GUVENMEZ
                     yalnizca imzali initData kabul eder
                            |
                   KeenDNS / tunel uzerinden internet
```

Genel portun başlığa güvenmemesi kritik: aksi halde adresi bilen herkes
`X-Remote-User-Id` başlığını uydurup istediği kullanıcı gibi davranabilirdi.

---

## KeenDNS ile public adres (Keenetic modem)

Keenetic modemler **KeenDNS** adında ücretsiz bir alan adı hizmeti sunar ve
geçerli bir HTTPS sertifikası sağlar — Telegram'ın tek şartı budur.

### Hangi mod?

KeenDNS iki modda çalışır ve aralarındaki fark yalnızca teknik değil, gizlilik
açısından da önemlidir:

- **Doğrudan erişim** — servis sağlayıcın sana gerçek (public) IP veriyorsa
  kullanılabilir. Trafik doğrudan modeme gelir, TLS uçtan uca senin cihazına
  kadar şifreli kalır. **Tercih edilen mod.**
- **Bulut üzerinden** — CGNAT arkasındaysan çalışır, ancak trafik Keenetic'in
  sunucuları üzerinden röle edilir ve TLS orada sonlanır. Harcama verilerin
  teknik olarak üçüncü bir tarafın altyapısından geçer. Kabul edilebilir olup
  olmadığına bilerek karar ver.

Hangi modda olduğunu KeenDNS ayar sayfası söyler; doğrudan erişim mümkün
değilse arayüz bunu belirtir.

### Adımlar

1. Modem arayüzüne gir (genellikle `http://192.168.1.1` veya `my.keenetic.net`).
2. **Alan adı** (KeenDNS) bölümünü aç.
3. Bir ad seç ve kaydet; `birsey.keenetic.pro` gibi bir adres alırsın.
4. Aynı bölümde bir **yayınlama / reverse proxy** kuralı ekle:
   - Hedef: Raspberry Pi'nin yerel IP'si
   - Port: **8100**
   - Protokol: HTTP (dış tarafta HTTPS'i KeenDNS sağlar)
5. Kaydet ve adresi bir tarayıcıda aç. Harcama formunu görüyorsan yol açıktır.
   (Kimlik doğrulaması olmadan form veri gösteremez; "yetkiniz yok" mesajı
   almak da adresin çalıştığı anlamına gelir.)

Menü adları firmware sürümüne göre değişebilir; aradığın şey "alan adı" ve
"yayınlama / uygulama yayınlama" başlıklarıdır.

### Add-on tarafı

1. Home Assistant'ta eklenti **Yapılandırma** sekmesini aç.
2. `webapp_public_url` alanına adresi yaz:

   ```
   https://birsey.keenetic.pro
   ```

3. Eklentiyi yeniden başlat. Günlükte şunu görmelisin:

   ```
   Telegram Mini App sunucusu başlatılıyor (port 8100)
   ```

Bu alan boşken ikinci süreç hiç başlatılmaz; gereksiz yere port açılmaz.

### BotFather tarafı

Telegram'ın menü düğmesinden formu açması için:

1. **@BotFather**'a `/mybots` yaz.
2. Botunu seç → **Bot Settings** → **Menu Button** → **Configure menu button**.
3. Adresi gir (`https://birsey.keenetic.pro`) ve düğme metni olarak
   `Harcama Ekle` yaz.

Bundan sonra bot menüsündeki **➕ Harcama Ekle** formu Telegram içinde açar.

---

## Alternatif: Cloudflare Tunnel

Keenetic kullanmıyorsan veya KeenDNS'in bulut modundan kaçınmak istiyorsan
Cloudflare Tunnel ücretsiz bir seçenektir. Kendi alan adını gerektirir ancak
modemde port açmayı gerektirmez. Tüneli Raspberry Pi'nin `8100` portuna
yönlendir, gerisi aynıdır.

---

## Doğrulama

Kurulum sonrası bunları kontrol et:

| Kontrol | Beklenen |
|---|---|
| HA panelinde **Bütçe** görünüyor mu | evet |
| Panelden harcama kaydedilebiliyor mu | evet |
| Bota `/start` yanıt veriyor mu | evet |
| Yetkisiz bir hesap bota yazınca | yalnızca `⛔` mesajı |
| `https://<adres>/health` | `{"status":"ok"}` |
| Telegram menü düğmesi formu açıyor mu | evet (Mini App kurulduysa) |

Adres dışarıdan açıldığında `health` dışında hiçbir uç kimlik doğrulaması
olmadan veri döndürmez; bunu doğrulamak istersen `https://<adres>/api/bootstrap`
adresini tarayıcıda aç, `401` almalısın.
