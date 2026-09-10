# Home Assistant OS Dağıtımı ve KeenDNS

Home Assistant OS burada yalnızca sunucuyu çalıştıran makinedir. Eklenti iki
giriş sunar:

| Giriş | Kimlik | Nereden açılır |
|---|---|---|
| **Web sitesi** (port 8100) | kullanıcı adı ve şifre | ev ağından `http://homeassistant.local:8100`, dışarıdan KeenDNS adresi |
| **Home Assistant paneli** (Ingress) | HA oturumu | HA'nın sol menüsündeki **Bütçe** |

Eklentinin kurulumu ve ayarları `budget_addon/DOCS.md` içindedir. Bu belge
sitenin internete güvenli biçimde açılmasını anlatır.

---

## İki süreç, bilinçli ayrım

```
                Home Assistant Supervisor agi
                            |
                     port 8099 (Ingress)
                     X-Remote-User-Id'ye GUVENIR
                     hatirlatmalar ve sensorler burada calisir
                            |
                     [ ayni kod, ayni veritabani ]
                            |
                     port 8100 (web sitesi)
                     Basliga GUVENMEZ
                     yalnizca sifreyle verilen oturum cerezi
                            |
                   KeenDNS (HTTPS) uzerinden internet
```

Web sitesi portunun başlığa güvenmemesi kritik: aksi halde adresi bilen herkes
`X-Remote-User-Id` başlığını uydurup istediği kullanıcı gibi davranabilirdi.

---

## KeenDNS ile HTTPS adres (Keenetic modem)

Keenetic modemler **KeenDNS** adında ücretsiz bir alan adı hizmeti sunar ve
adres için geçerli bir HTTPS sertifikasını kendisi alır. Modemde port açmak
gerekmez; modem gelen HTTPS isteğini ev ağındaki Raspberry Pi'ye iletir.

### Hangi mod?

KeenDNS iki modda çalışır ve aralarındaki fark yalnızca teknik değil, gizlilik
açısından da önemlidir:

- **Doğrudan erişim** — servis sağlayıcın sana gerçek (public) IP veriyorsa
  kullanılabilir. Trafik doğrudan modeme gelir; HTTPS modemde sonlanır.
  **Tercih edilen mod.**
- **Bulut üzerinden** — CGNAT arkasındaysan çalışır, ancak trafik Keenetic'in
  sunucuları üzerinden röle edilir. Harcama verilerin teknik olarak üçüncü bir
  tarafın altyapısından geçer. Kabul edilebilir olup olmadığına bilerek karar
  ver.

Hangi modda olduğunu KeenDNS ayar sayfası söyler; doğrudan erişim mümkün
değilse arayüz bunu belirtir.

### 1. Raspberry Pi'ye sabit IP ver

Modem arayüzünde (`http://192.168.1.1` veya `my.keenetic.net`) **Cihaz
listesi**'nde Raspberry Pi'yi bul, **Kayıtlı** yap ve **Sabit IP adresi**
işaretle. Aksi halde IP değiştiğinde yönlendirme boşa düşer.

### 2. KeenDNS adını al

**Ağ kuralları → Alan adı** (bazı sürümlerde **Yönetim → KeenDNS**) bölümünde
bir ad seç ve kaydet. `evim.keenetic.pro` gibi bir adres alırsın.

### 3. Siteyi yayınla

Aynı sayfadaki **Ev ağındaki web uygulamaları** listesine **Ekle**:

| Alan | Değer |
|---|---|
| Ad | `butce` → adres `butce.evim.keenetic.pro` olur |
| Cihaz | Raspberry Pi |
| Protokol | HTTP (dış tarafta HTTPS'i KeenDNS sağlar) |
| Port | `8100` |
| Erişim | **Kimlik doğrulaması olmadan / herkese açık** |

Erişimi modem şifresine bağlama: aile üyelerinin modem yöneticisi şifresini
bilmesi gerekirdi. Site kendi kullanıcı adı ve şifresiyle korunur.

Menü adları firmware sürümüne göre değişebilir; aradığın şey "alan adı" ve
"web uygulaması yayınlama" başlıklarıdır.

### 4. Eklentiye adresi söyle

1. Home Assistant'ta eklentinin **Yapılandırma** sekmesini aç.
2. `site_url` alanına adresi yaz:

   ```
   https://butce.evim.keenetic.pro
   ```

3. **Ağ** bölümünde 8100 portunun açık olduğundan emin ol (varsayılan
   `8100`).
4. Eklentiyi yeniden başlat.

---

## Alternatif: Cloudflare Tunnel

Keenetic kullanmıyorsan veya KeenDNS'in bulut modundan kaçınmak istiyorsan
Cloudflare Tunnel ücretsiz bir seçenektir. Kendi alan adını gerektirir ancak
modemde port açmayı gerektirmez. Tüneli Raspberry Pi'nin `8100` portuna
yönlendir ve `site_url` alanına tünelin adresini yaz.

---

## Doğrulama

| Kontrol | Beklenen |
|---|---|
| `https://butce.evim.keenetic.pro/health` | `{"status":"ok"}` |
| Adresin kendisi | giriş ekranı; tarayıcıda kilit simgesi, sertifika uyarısı yok |
| `https://butce.evim.keenetic.pro/api/bootstrap` (giriş yapmadan) | `401` |
| Telefonun mobil verisiyle (Wi-Fi kapalı) giriş | özet ekranı açılır |
| **Ayarlar → Bildirimler → Deneme gönder** | anlık bildirim telefona gelir |
| HA panelinde **Bütçe** | aynı veri, şifre sormadan |

Adres dışarıdan açıldığında `health` dışında hiçbir uç kimlik doğrulaması
olmadan veri döndürmez.
