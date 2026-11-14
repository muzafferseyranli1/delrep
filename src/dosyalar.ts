import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { unzipSync } from "fflate";

/**
 * Yüklenen rapor dosyalarının saklanması: .xlsx ve .csv doğrudan, .zip ise içindeki .xlsx/.csv dosyaları açılarak.
 * Hangi raporun ne olduğunu analiz (analiz/okuma.py) dosyanın içeriğinden anlar; burada yalnız biçim denetlenir.
 * Hiçbir dosya ezilmez: aynı içerik ikinci kez gelirse atlanır, aynı adla farklı içerik gelirse adına sayı eklenir.
 * Aynı kayıt birden çok dosyada olursa analiz en yeni yüklenen dosyadakini kullanır.
 */

export const AZAMI_DOSYA_BAYT = 100 * 1024 * 1024;
const ZIP_AZAMI_GIRIS = 500;
const ZIP_AZAMI_TEK = 100 * 1024 * 1024;
const ZIP_AZAMI_TOPLAM = 300 * 1024 * 1024;
const UZANTILAR = [".xlsx", ".csv"];

export class DosyaHatasi extends Error {
  constructor(
    mesaj: string,
    public status = 400,
  ) {
    super(mesaj);
  }
}

/** Yol ayırıcılarını atar, harf/rakam/nokta/boşluk/parantez/+/- dışını "_" yapar. Geçersizse undefined. */
export function guvenliAd(ham: string): string | undefined {
  const son = ham.normalize("NFC").split(/[\\/]/).pop() ?? "";
  const temiz = son.replace(/[^\p{L}\p{N}._ ()+-]/gu, "_").replace(/\s+/g, " ").trim();
  if (!temiz || temiz.startsWith(".") || temiz.length > 150) return undefined;
  return temiz;
}

/** Uzantıyı küçük harfe çevirir (Linux'ta büyük/küçük harf ayrımı vardır). */
function uzantiKucuk(ad: string): string {
  return ad.replace(/\.(xlsx|csv|zip)$/i, (m) => m.toLowerCase());
}

const pkMi = (b: Uint8Array) => b.length > 4 && b[0] === 0x50 && b[1] === 0x4b && b[2] === 3 && b[3] === 4;

/** CSV metin olmalı: ilk 8 KB'ta NUL baytı olmamalı ve boş olmamalı. */
const metinMi = (b: Uint8Array) => b.length > 0 && !b.subarray(0, 8192).includes(0);

/** Saklanabilir tek dosya mı (zip dışı)? Uzantı ve içerik birlikte denetlenir. */
function gecerliIcerik(ad: string, veri: Uint8Array): boolean {
  const lower = ad.toLowerCase();
  if (lower.endsWith(".xlsx")) return pkMi(veri);
  if (lower.endsWith(".csv")) return metinMi(veri);
  return false;
}

const ozet = (veri: Uint8Array) => createHash("sha256").update(veri).digest("hex");

/** Klasördeki dosyaların içerik özetleri (aynı dosyanın ikinci kez saklanmaması için). */
async function mevcutOzetler(dir: string): Promise<Map<string, string>> {
  const m = new Map<string, string>();
  let adlar: string[] = [];
  try {
    adlar = await readdir(dir);
  } catch {
    return m;
  }
  for (const ad of adlar) {
    if (ad.endsWith(".tmp")) continue;
    const yol = path.join(dir, ad);
    if (!(await stat(yol)).isFile()) continue;
    m.set(ozet(await readFile(yol)), ad);
  }
  return m;
}

/** Ad doluysa "ad (2).csv", "ad (3).csv"… dener. */
function bosAd(ad: string, dolu: Set<string>): string {
  if (!dolu.has(ad.toLowerCase())) return ad;
  const nokta = ad.lastIndexOf(".");
  const govde = nokta > 0 ? ad.slice(0, nokta) : ad;
  const uzanti = nokta > 0 ? ad.slice(nokta) : "";
  for (let n = 2; ; n++) {
    const aday = `${govde} (${n})${uzanti}`;
    if (!dolu.has(aday.toLowerCase())) return aday;
  }
}

async function yaz(dir: string, ad: string, veri: Uint8Array): Promise<void> {
  const hedef = path.join(dir, ad);
  const tmp = `${hedef}.${process.pid}.tmp`;
  await writeFile(tmp, veri);
  await rename(tmp, hedef); // yarım yazılmış dosya analize girmez
}

export interface KayitSonucu {
  kaydedilen: string[];
  /** Daha önce yüklenmiş, birebir aynı içerikli dosyalar (yeniden saklanmadı). */
  zatenVar: string[];
  /** ZIP içinde .xlsx/.csv olmadığı ya da bozuk olduğu için atlanan dosya sayısı. */
  atlanan: number;
}

export async function kaydet(dir: string, hamAd: string, veri: Buffer): Promise<KayitSonucu> {
  const guvenli = guvenliAd(hamAd);
  if (!guvenli) throw new DosyaHatasi("Geçersiz dosya adı.");
  const ad = uzantiKucuk(guvenli);
  const lower = ad.toLowerCase();
  const zipMi = lower.endsWith(".zip");
  if (!zipMi && !UZANTILAR.some((u) => lower.endsWith(u))) {
    throw new DosyaHatasi("Yalnızca .xlsx, .csv veya .zip dosyası yüklenebilir.");
  }

  let parcalar: [string, Uint8Array][];
  let atlanan = 0;
  if (!zipMi) {
    if (!gecerliIcerik(ad, veri)) throw new DosyaHatasi(`Dosya geçerli bir ${lower.endsWith(".csv") ? ".csv" : ".xlsx"} değil.`);
    parcalar = [[ad, new Uint8Array(veri)]];
  } else {
    if (!pkMi(veri)) throw new DosyaHatasi("Dosya geçerli bir .zip değil.");
    let sayi = 0;
    let toplam = 0;
    let icerik: Record<string, Uint8Array>;
    try {
      icerik = unzipSync(new Uint8Array(veri), {
        filter: (f) => {
          if (f.name.endsWith("/") || f.name.startsWith("__MACOSX/")) return false;
          const taban = (f.name.split("/").pop() ?? "").toLowerCase();
          if (taban.startsWith("._")) return false;
          if (!UZANTILAR.some((u) => taban.endsWith(u))) {
            atlanan += 1;
            return false;
          }
          sayi += 1;
          toplam += f.originalSize;
          if (sayi > ZIP_AZAMI_GIRIS) throw new DosyaHatasi("ZIP içinde çok fazla dosya var.");
          if (f.originalSize > ZIP_AZAMI_TEK || toplam > ZIP_AZAMI_TOPLAM) throw new DosyaHatasi("ZIP içeriği çok büyük.");
          return true;
        },
      });
    } catch (e) {
      if (e instanceof DosyaHatasi) throw e;
      throw new DosyaHatasi("ZIP dosyası açılamadı.");
    }
    parcalar = [];
    for (const [yol, v] of Object.entries(icerik)) {
      const temel = guvenliAd(yol);
      if (!temel || !gecerliIcerik(temel, v)) {
        atlanan += 1;
        continue;
      }
      parcalar.push([uzantiKucuk(temel), v]);
    }
    if (!parcalar.length) throw new DosyaHatasi("ZIP içinde geçerli bir .xlsx ya da .csv dosyası yok.");
  }

  await mkdir(dir, { recursive: true });
  const ozetler = await mevcutOzetler(dir);
  const dolu = new Set([...ozetler.values()].map((a) => a.toLowerCase()));
  const kaydedilen: string[] = [];
  const zatenVar: string[] = [];
  for (const [parcaAd, v] of parcalar) {
    const h = ozet(v);
    const eski = ozetler.get(h);
    if (eski) {
      zatenVar.push(eski);
      continue;
    }
    const hedef = bosAd(parcaAd, dolu);
    await yaz(dir, hedef, v);
    dolu.add(hedef.toLowerCase());
    ozetler.set(h, hedef);
    kaydedilen.push(hedef);
  }
  return { kaydedilen, zatenVar, atlanan };
}

export interface DosyaBilgisi {
  ad: string;
  bayt: number;
  tarih: string;
  /** Son analizin bu dosyaya verdiği tür (ör. "Yemeksepeti sipariş listesi"); analiz edilmediyse null. */
  tur: string | null;
  /** Son analizdeki durum: "okundu", "kopya (…)", "tanınmadı …" vb.; analiz edilmediyse null. */
  durum: string | null;
}

interface AnalizOzeti {
  dosyalar?: { ad: string; tur?: string; durum?: string }[];
}

/** Saklanan dosyalar; analiz özeti (ozet.json) varsa her dosyanın türü ve durumuyla. */
export async function listele(dir: string, ozetYolu?: string): Promise<DosyaBilgisi[]> {
  let adlar: string[];
  try {
    adlar = await readdir(dir);
  } catch {
    return [];
  }
  const analiz = new Map<string, { tur: string | null; durum: string | null }>();
  if (ozetYolu) {
    try {
      const o = JSON.parse(await readFile(ozetYolu, "utf8")) as AnalizOzeti;
      // Sunucu zipleri açarak saklar; özetteki adlar klasördeki dosya adlarıyla aynıdır
      for (const d of o.dosyalar ?? []) analiz.set(d.ad, { tur: d.tur || null, durum: d.durum || null });
    } catch {
      /* henüz analiz yok */
    }
  }
  const sonuc: DosyaBilgisi[] = [];
  for (const ad of adlar) {
    const lower = ad.toLowerCase();
    if (ad.endsWith(".tmp") || !UZANTILAR.some((u) => lower.endsWith(u))) continue;
    const s = await stat(path.join(dir, ad));
    if (!s.isFile()) continue;
    const a = analiz.get(ad);
    sonuc.push({ ad, bayt: s.size, tarih: s.mtime.toISOString(), tur: a?.tur ?? null, durum: a?.durum ?? null });
  }
  return sonuc.sort((a, b) => a.ad.localeCompare(b.ad, "tr"));
}

export async function sil(dir: string, ad: string): Promise<void> {
  if (guvenliAd(ad) !== ad) throw new DosyaHatasi("Geçersiz dosya adı.");
  await rm(path.join(dir, ad), { force: true });
}
