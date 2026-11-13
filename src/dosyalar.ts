import { mkdir, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { unzipSync } from "fflate";

/** Yüklenen fatura dosyalarının saklanması: .xlsx doğrudan, .zip ise içindeki .xlsx dosyaları açılarak. */

export const AZAMI_DOSYA_BAYT = 100 * 1024 * 1024;
const ZIP_AZAMI_GIRIS = 500;
const ZIP_AZAMI_TEK = 100 * 1024 * 1024;
const ZIP_AZAMI_TOPLAM = 300 * 1024 * 1024;

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

/** Uzantıyı küçük harfe çevirir: analiz betiği "*.xlsx" arar, Linux'ta büyük/küçük harf ayrımı vardır. */
function uzantiKucuk(ad: string): string {
  return ad.replace(/\.(xlsx|zip)$/i, (m) => m.toLowerCase());
}

const pkMi = (b: Uint8Array) => b.length > 4 && b[0] === 0x50 && b[1] === 0x4b && b[2] === 3 && b[3] === 4;

/** Analizin okuyabildiği dosya: Trendyol Go / GetirYemek faturaları. */
export function taninir(ad: string): boolean {
  return /SaticiFatura|PayWithOnDelivery/i.test(ad) && ad.toLowerCase().endsWith(".xlsx");
}

async function yaz(dir: string, ad: string, veri: Uint8Array): Promise<void> {
  const hedef = path.join(dir, ad);
  const tmp = `${hedef}.${process.pid}.tmp`;
  await writeFile(tmp, veri);
  await rename(tmp, hedef); // yarım yazılmış dosya analize girmez
}

export interface KayitSonucu {
  kaydedilen: string[];
  /** ZIP içinde .xlsx olmadığı için atlanan dosya sayısı. */
  atlanan: number;
}

export async function kaydet(dir: string, hamAd: string, veri: Buffer): Promise<KayitSonucu> {
  const guvenli = guvenliAd(hamAd);
  if (!guvenli) throw new DosyaHatasi("Geçersiz dosya adı.");
  const ad = uzantiKucuk(guvenli);
  const lower = ad.toLowerCase();
  if (!lower.endsWith(".xlsx") && !lower.endsWith(".zip")) throw new DosyaHatasi("Yalnızca .xlsx veya .zip dosyası yüklenebilir.");
  if (!pkMi(veri)) throw new DosyaHatasi("Dosya geçerli bir .xlsx veya .zip değil.");
  await mkdir(dir, { recursive: true });

  if (lower.endsWith(".xlsx")) {
    await yaz(dir, ad, veri);
    return { kaydedilen: [ad], atlanan: 0 };
  }

  let sayi = 0;
  let atlanan = 0;
  let toplam = 0;
  let icerik: Record<string, Uint8Array>;
  try {
    icerik = unzipSync(new Uint8Array(veri), {
      filter: (f) => {
        if (f.name.endsWith("/") || f.name.startsWith("__MACOSX/")) return false;
        const taban = f.name.split("/").pop() ?? "";
        if (taban.startsWith("._")) return false;
        if (!taban.toLowerCase().endsWith(".xlsx")) {
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

  const kaydedilen: string[] = [];
  const kullanilan = new Set<string>();
  for (const [yol, icerikVeri] of Object.entries(icerik)) {
    if (!pkMi(icerikVeri)) {
      atlanan += 1;
      continue;
    }
    const temel = guvenliAd(yol);
    if (!temel) {
      atlanan += 1;
      continue;
    }
    let hedef = uzantiKucuk(temel);
    // Farklı klasörlerde aynı adlı dosya: ikincisinin başına sayaç eklenir, biri ötekini ezmez
    for (let n = 2; kullanilan.has(hedef.toLowerCase()); n++) hedef = `${n}_${uzantiKucuk(temel)}`;
    kullanilan.add(hedef.toLowerCase());
    await yaz(dir, hedef, icerikVeri);
    kaydedilen.push(hedef);
  }
  if (!kaydedilen.length) throw new DosyaHatasi("ZIP içinde geçerli bir .xlsx dosyası yok.");
  return { kaydedilen, atlanan };
}

export interface DosyaBilgisi {
  ad: string;
  bayt: number;
  tarih: string;
  /** Analiz bu dosyayı okuyabiliyor mu (Trendyol Go / GetirYemek). */
  taninan: boolean;
}

export async function listele(dir: string): Promise<DosyaBilgisi[]> {
  let adlar: string[];
  try {
    adlar = await readdir(dir);
  } catch {
    return [];
  }
  const sonuc: DosyaBilgisi[] = [];
  for (const ad of adlar) {
    if (ad.endsWith(".tmp") || !ad.toLowerCase().endsWith(".xlsx")) continue;
    const s = await stat(path.join(dir, ad));
    if (!s.isFile()) continue;
    sonuc.push({ ad, bayt: s.size, tarih: s.mtime.toISOString(), taninan: taninir(ad) });
  }
  return sonuc.sort((a, b) => a.ad.localeCompare(b.ad, "tr"));
}

export async function sil(dir: string, ad: string): Promise<void> {
  if (guvenliAd(ad) !== ad) throw new DosyaHatasi("Geçersiz dosya adı.");
  await rm(path.join(dir, ad), { force: true });
}
