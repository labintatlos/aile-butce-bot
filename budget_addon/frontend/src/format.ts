/**
 * Türkçe biçimlendirme.
 *
 * Tutarlar sunucuda kuruş olarak tutulur ve biçimlenmiş metinle birlikte
 * gelir. İstemci para hesabı yapmaz; buradaki çeviriler yalnızca kullanıcının
 * yazdığı tutarı kuruşa çevirmek ve kuruş toplamlarını göstermek içindir.
 * İkisi de sunucudaki `parse_amount_to_minor` ve `format_try` kurallarının
 * birebir aynısıdır; tamsayı kuruşla çalışır, kayan nokta kullanmaz.
 */

const MONTHS = [
  "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
];

function parts(iso: string): [number, number, number] {
  const [year, month, day] = iso.split("-").map(Number);
  return [year, month, day];
}

/** `2026-09-02` -> `2 Eylül 2026` */
export function longDate(iso: string): string {
  const [year, month, day] = parts(iso);
  if (!year || !month || !day) return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/** `2026-09-02` -> `2 Eyl` (bu yıl) veya `2 Eyl 2025` */
export function shortDate(iso: string): string {
  const [year, month, day] = parts(iso);
  if (!year || !month || !day) return iso;
  const base = `${day} ${MONTHS[month - 1].slice(0, 3)}`;
  return year === new Date().getFullYear() ? base : `${base} ${year}`;
}

export function yearMonthOf(iso: string): { year: number; month: number } {
  const [year, month] = parts(iso);
  return { year, month };
}

/**
 * Tutar alanindaki yaziyi temizler.
 *
 * Rakam, nokta ve virgul disindaki her sey atilir. Asil dogrulama sunucuda
 * yapilir; burada amac yalnizca yanlis karakter yazilmasini engellemektir.
 */
export function sanitiseAmount(raw: string): string {
  return raw.replace(/[^\d.,]/g, "").slice(0, 20);
}

export function looksLikeAmount(raw: string): boolean {
  return /\d/.test(raw);
}

const CURRENCY_NOISE = ["₺", "TL", "tl", " ", " "];

/**
 * Kullanıcı girdisini kuruşa çevirir; geçersiz veya sıfırsa `null`.
 *
 * `1250`, `1250,50`, `1.250,50`, `1250.50` kabul edilir. Virgül yoksa ve tek
 * noktadan sonra tam üç basamak varsa nokta binlik ayracıdır (`1.250` = 1250).
 */
export function parseAmountToMinor(raw: string): number | null {
  let text = raw;
  for (const token of CURRENCY_NOISE) text = text.split(token).join("");
  text = text.trim();
  if (!text) return null;

  if (text.includes(",")) {
    text = text.replace(/\./g, "").replace(/,/g, ".");
  } else if ((text.match(/\./g) ?? []).length > 1) {
    text = text.replace(/\./g, "");
  } else if (text.includes(".")) {
    const fraction = text.split(".")[1];
    if (fraction.length === 3 && /^\d+$/.test(fraction)) text = text.replace(".", "");
  }

  if (!/^(\d+\.?\d*|\.\d+)$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  let minor = Number(whole || "0") * 100 + Number((fraction + "00").slice(0, 2));
  // Sunucudaki ROUND_HALF_UP: ucuncu ondalik 5 veya ustuyse yukari yuvarlanir.
  if (fraction.length > 2 && Number(fraction[2]) >= 5) minor += 1;
  return minor > 0 ? minor : null;
}

/** Kuruşu `12.450,75 TL` biçiminde gösterir. */
export function formatMinor(minor: number): string {
  const absolute = Math.abs(minor);
  const major = Math.floor(absolute / 100);
  const cents = absolute % 100;
  const grouped = String(major).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const text = `${grouped},${String(cents).padStart(2, "0")} TL`;
  return minor < 0 ? `-${text}` : text;
}

/** Kuruşu düzenleme alanına yazılacak hâle getirir: 125050 -> `1250,50`. */
export function minorToInput(minor: number): string {
  return `${Math.floor(minor / 100)},${String(minor % 100).padStart(2, "0")}`;
}

export function installmentLabel(count: number): string {
  return count <= 1 ? "Peşin" : `${count} Taksit`;
}

/** `2026`, `9` -> `Eylül 2026` */
export function monthName(year: number, month: number): string {
  return `${MONTHS[month - 1]} ${year}`;
}

/** Ay adının kısa hâli; grafikte eksen etiketi olarak kullanılır. */
export function shortMonthName(month: number): string {
  return MONTHS[month - 1].slice(0, 3);
}
