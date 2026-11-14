import { execFile } from "node:child_process";
import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";

/** Yüklenen faturaları Python analiz betiğiyle işler ve HTML raporu üretir. */

export interface AnalizSonucu {
  ok: boolean;
  mesaj: string;
}
export type AnalizCalistirici = () => Promise<AnalizSonucu>;

export interface AnalizAyarlari {
  dataDir: string;
  /** Üretilen raporun yazılacağı yer (sunulan index.html). */
  reportPath: string;
  pythonBin?: string;
  /** analiz/calistir.py klasörü. */
  analizDir?: string;
}

const ZAMAN_ASIMI_MS = 180_000;

function calistir(a: AnalizAyarlari): Promise<AnalizSonucu> {
  const python = a.pythonBin || "python3";
  const analizDir = a.analizDir || path.resolve("analiz");
  const faturalar = path.join(a.dataDir, "faturalar");
  const cikti = path.join(a.dataDir, "analiz-cikti");
  const gecici = `${a.reportPath}.analiz.tmp`;

  return new Promise((resolve) => {
    void mkdir(path.dirname(a.reportPath), { recursive: true })
      .then(() => mkdir(faturalar, { recursive: true }))
      .then(() => {
        execFile(
          python,
          // -I ortam değişkenlerini (PYTHONIOENCODING dahil) yok sayar; çıktı kodlaması -X utf8 ile sabitlenir
          ["-I", "-X", "utf8", "-W", "ignore", path.join(analizDir, "calistir.py"), faturalar, cikti, gecici],
          {
            timeout: ZAMAN_ASIMI_MS,
            maxBuffer: 5 * 1024 * 1024,
            env: {
              PATH: process.env.PATH ?? "",
              ...(process.env.ANALIZ_BASLANGIC ? { ANALIZ_BASLANGIC: process.env.ANALIZ_BASLANGIC } : {}),
            },
          },
          (err, stdout, stderr) => {
            const sonSatir = (s: string) => s.trim().split(/\r?\n/).filter(Boolean).pop() ?? "";
            if (err) {
              void rm(gecici, { force: true });
              const zamanAsimi = (err as NodeJS.ErrnoException & { killed?: boolean }).killed;
              const neden = zamanAsimi ? "Analiz zaman aşımına uğradı." : sonSatir(String(stderr)) || sonSatir(String(stdout)) || err.message;
              return resolve({ ok: false, mesaj: neden.slice(0, 400) });
            }
            // Eski rapor ancak yenisi tamamen üretilince değişir
            rename(gecici, a.reportPath).then(
              () => resolve({ ok: true, mesaj: sonSatir(String(stdout)) || "Rapor güncellendi." }),
              (e: Error) => resolve({ ok: false, mesaj: `Rapor yazılamadı: ${e.message}` }),
            );
          },
        );
      })
      .catch((e: Error) => resolve({ ok: false, mesaj: e.message }));
  });
}

/** Aynı anda tek analiz çalışır; çalışırken gelen istek mevcut sonucu bekler. */
export function gercekCalistirici(a: AnalizAyarlari): AnalizCalistirici {
  let surerken: Promise<AnalizSonucu> | undefined;
  return () => {
    if (!surerken) surerken = calistir(a).finally(() => void (surerken = undefined));
    return surerken;
  };
}
