import { createHash, timingSafeEqual } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import express, { type Express, type NextFunction, type Request, type Response } from "express";
import type { AnalizCalistirici } from "./analiz";
import { AZAMI_DOSYA_BAYT, DosyaHatasi, kaydet, listele, sil } from "./dosyalar";
import { YUKLE_CSP, YUKLE_HTML } from "./yukle-sayfasi";

/**
 * Paket servis raporu.
 * Rapor iki yoldan gelir: /yukle sayfasından yüklenen Trendyol Go ve Yemeksepeti dosyalarından sunucuda üretilir
 * (analiz/calistir.py), ya da yerelde üretilip tek dosyalık HTML olarak buraya yüklenir:
 *   PUT /api/paketrapor   Authorization: Bearer <UPLOAD_TOKEN>
 * Sayfayı görmek için tarayıcı kullanıcı adı/şifre sorar (HTTP Basic, yalnızca HTTPS arkasında kullanın):
 *   GET /   (ya da /paketrapor)
 * Rapor kalıcı diskte tutulur; veri güncellemek için yeniden deploy gerekmez.
 */

/** Rapor dış kaynak kullanmaz: yalnız kendi satır içi stil ve betiği çalışır, hiçbir yere istek atamaz. */
export const RAPOR_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
const AZAMI_BOYUT = "5mb";
const DENEME_SINIRI = 10; // pencere başına IP başına hatalı deneme
const DENEME_PENCERESI_MS = 15 * 60 * 1000;

const BOS_SAYFA = `<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paket servis raporu</title></head><body style="font:16px system-ui,sans-serif;margin:40px">
<h1>Paket servis raporu</h1><p>Henüz rapor yok. <a href="/yukle">Fatura yükleyin</a>.</p></body></html>`;

export interface AppOptions {
  /** Raporun saklanacağı klasör (kalıcı volume). */
  dataDir: string;
  /** Yükleme jetonu, en az 32 karakter. Yoksa yükleme kapalı (503). */
  uploadToken?: string;
  /** Sayfayı görme şifresi, en az 12 karakter. Yoksa sayfa kapalı (503). */
  viewPassword?: string;
  /** Sayfa kullanıcı adı (varsayılan admin). */
  viewUser?: string;
  /** Yüklenen faturalardan raporu üretir; yoksa /api/analiz kapalıdır (501). */
  analizCalistir?: AnalizCalistirici;
}

const sha = (s: string) => createHash("sha256").update(s).digest();
const esit = (a: string, b: string) => timingSafeEqual(sha(a), sha(b));

/** Jeton en az 32 karakter olmalı; karşılaştırma sabit sürede yapılır. */
export function tokenValid(expected: string | undefined, authorization: string | undefined): boolean {
  if (!expected || expected.length < 32 || !authorization?.startsWith("Bearer ")) return false;
  return esit(expected, authorization.slice(7).trim());
}

/** "Basic base64(kullanici:sifre)" başlığını doğrular. */
export function basicValid(user: string, password: string | undefined, authorization: string | undefined): boolean {
  if (!password || password.length < 12 || !authorization?.startsWith("Basic ")) return false;
  const cozulen = Buffer.from(authorization.slice(6).trim(), "base64").toString("utf8");
  const i = cozulen.indexOf(":");
  if (i < 0) return false;
  // İki karşılaştırma da her zaman yapılır (kısa devre yok)
  const kullaniciTamam = esit(cozulen.slice(0, i), user);
  const sifreTamam = esit(cozulen.slice(i + 1), password);
  return kullaniciTamam && sifreTamam;
}

export function reportFile(dir: string): string {
  return path.join(dir, "index.html");
}

/** Bellekte basit hatalı deneme sınırlayıcı (tek süreç için yeterli). */
function denemeSinirlayici() {
  const kayit = new Map<string, { sayi: number; bitis: number }>();
  const aktif = (ip: string) => {
    const k = kayit.get(ip);
    if (!k || k.bitis < Date.now()) return undefined;
    return k;
  };
  return {
    engelli: (ip: string) => (aktif(ip)?.sayi ?? 0) >= DENEME_SINIRI,
    hata: (ip: string) => {
      const k = aktif(ip);
      if (k) k.sayi += 1;
      else kayit.set(ip, { sayi: 1, bitis: Date.now() + DENEME_PENCERESI_MS });
      if (kayit.size > 5000) for (const [key, v] of kayit) if (v.bitis < Date.now()) kayit.delete(key);
    },
    temizle: (ip: string) => void kayit.delete(ip),
  };
}

export function createApp(opts: AppOptions): Express {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // Coolify (Traefik) arkasında gerçek IP için
  const user = opts.viewUser?.trim() || "admin";
  const sinir = denemeSinirlayici();

  // Sağlık kontrolü: kimlik doğrulama yok, bilgi sızdırmaz
  app.get("/health", (_req, res) => void res.json({ ok: true }));

  // Yükleme ucu: jetonla doğrulanır
  app.put("/api/paketrapor", express.text({ type: () => true, limit: AZAMI_BOYUT }), async (req, res) => {
    if (!opts.uploadToken) return void res.status(503).json({ error: "UPLOAD_TOKEN tanımlı değil: yükleme kapalı." });
    const ip = req.ip ?? "?";
    if (sinir.engelli(ip)) return void res.status(429).json({ error: "Çok fazla hatalı deneme. Daha sonra tekrar deneyin." });
    if (!tokenValid(opts.uploadToken, req.headers.authorization)) {
      sinir.hata(ip);
      return void res.status(401).json({ error: "Geçersiz jeton." });
    }
    const html = typeof req.body === "string" ? req.body : "";
    if (!/^\s*<!doctype html/i.test(html)) return void res.status(400).json({ error: "Tek dosyalık HTML rapor bekleniyor." });
    await mkdir(opts.dataDir, { recursive: true });
    const target = reportFile(opts.dataDir);
    const tmp = `${target}.${process.pid}.tmp`;
    await writeFile(tmp, html, "utf8");
    await rename(tmp, target); // yarım yazılmış dosya hiç sunulmaz
    res.json({ ok: true, bytes: Buffer.byteLength(html, "utf8") });
  });

  // Sayfa: HTTP Basic ile korunur
  const girisGerekli = (req: Request, res: Response, next: NextFunction) => {
    if (!opts.viewPassword || opts.viewPassword.length < 12) {
      return void res.status(503).type("text").send("VIEW_PASSWORD tanımlı değil (en az 12 karakter): sayfa kapalı.");
    }
    const ip = req.ip ?? "?";
    if (sinir.engelli(ip)) return void res.status(429).type("text").send("Çok fazla hatalı deneme. Daha sonra tekrar deneyin.");
    if (!basicValid(user, opts.viewPassword, req.headers.authorization)) {
      if (req.headers.authorization) sinir.hata(ip);
      res.setHeader("WWW-Authenticate", 'Basic realm="Paket servis raporu", charset="UTF-8"');
      return void res.status(401).type("text").send("Giriş gerekli.");
    }
    sinir.temizle(ip);
    next();
  };

  const sayfa = async (_req: Request, res: Response) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Security-Policy", RAPOR_CSP);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    try {
      res.type("html").send(await readFile(reportFile(opts.dataDir), "utf8"));
    } catch {
      res.status(404).type("html").send(BOS_SAYFA);
    }
  };
  app.get(["/", "/paketrapor"], girisGerekli, sayfa);

  // --- Fatura yükleme: oturum yerine Basic kimlik, değiştiren uçlarda özel başlık (çapraz site isteği ön kontrolde elenir) ---
  const faturaDir = path.join(opts.dataDir, "faturalar");
  const ajax = (req: Request, res: Response, next: NextFunction) =>
    req.headers["x-requested-with"] === "delrep" ? next() : void res.status(400).json({ error: "Geçersiz istek." });
  const hata = (res: Response, e: unknown) => {
    if (e instanceof DosyaHatasi) return void res.status(e.status).json({ error: e.message });
    console.error(e);
    res.status(500).json({ error: "Sunucu hatası." });
  };

  app.get("/yukle", girisGerekli, (_req, res) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Security-Policy", YUKLE_CSP);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.type("html").send(YUKLE_HTML);
  });

  app.get("/api/dosyalar", girisGerekli, async (_req, res) => {
    try {
      res.setHeader("Cache-Control", "no-store");
      res.json({ dosyalar: await listele(faturaDir, path.join(opts.dataDir, "analiz-cikti", "ozet.json")) });
    } catch (e) {
      hata(res, e);
    }
  });

  app.put("/api/dosyalar/:ad", girisGerekli, ajax, express.raw({ type: () => true, limit: AZAMI_DOSYA_BAYT }), async (req, res) => {
    try {
      const veri = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
      res.json({ ok: true, ...(await kaydet(faturaDir, req.params.ad, veri)) });
    } catch (e) {
      hata(res, e);
    }
  });

  app.delete("/api/dosyalar/:ad", girisGerekli, ajax, async (req, res) => {
    try {
      await sil(faturaDir, req.params.ad);
      res.json({ ok: true });
    } catch (e) {
      hata(res, e);
    }
  });

  app.post("/api/analiz", girisGerekli, ajax, async (_req, res) => {
    if (!opts.analizCalistir) return void res.status(501).json({ ok: false, error: "Analiz yapılandırılmamış." });
    try {
      const sonuc = await opts.analizCalistir();
      res.status(sonuc.ok ? 200 : 422).json(sonuc);
    } catch (e) {
      hata(res, e);
    }
  });

  // Gövde sınırı vb. hatalar JSON döner
  app.use((err: { status?: number; statusCode?: number }, _req: Request, res: Response, _next: NextFunction) => {
    const s = err.status ?? err.statusCode ?? 500;
    res.status(s).json({ error: s === 413 ? "Dosya çok büyük (en çok 100 MB)." : "İstek işlenemedi." });
  });

  return app;
}
