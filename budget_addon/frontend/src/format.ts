/**
 * Türkçe biçimlendirme.
 *
 * Tutarlar sunucuda kuruş olarak tutulur ve biçimlenmiş metinle birlikte
 * gelir; burada yalnızca kullanıcının yazdığı serbest metin düzenlenir.
 * İstemci hiçbir zaman kendi başına para aritmetiği yapmaz.
 */

const MONTHS = [
  "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
];

/** `2026-09-02` -> `2 Eylül 2026` */
export function longDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/**
 * Tutar alanindaki yaziyi temizler.
 *
 * Rakam, nokta ve virgul disindaki her sey atilir. Dogrulama ve kurusa cevirme
 * sunucuda yapilir; burada amac yalnizca kullaniciyi yanlis karakter
 * yazmaktan korumaktir.
 */
export function sanitiseAmount(raw: string): string {
  return raw.replace(/[^\d.,]/g, "").slice(0, 20);
}

export function looksLikeAmount(raw: string): boolean {
  return /\d/.test(raw);
}

export function installmentLabel(count: number): string {
  return count <= 1 ? "Peşin" : `${count} Taksit`;
}

/** `2026`, `9` -> `Eylül 2026` */
export function monthName(year: number, month: number): string {
  return `${MONTHS[month - 1]} ${year}`;
}

/** Ay adının kısa hâli; yıllık grafikte eksen etiketi olarak kullanılır. */
export function shortMonthName(month: number): string {
  return MONTHS[month - 1].slice(0, 3);
}

/**
 * Oranı yüzde olarak sınırlar.
 *
 * Grafik çubuğu taşan bir değerle çizilirse kutunun dışına akar; oran
 * metinde yine gerçek hâliyle gösterilir.
 */
export function barWidth(ratio: number): string {
  return `${Math.min(Math.max(ratio, 0), 100)}%`;
}
