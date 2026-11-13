import assert from "node:assert/strict";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { zipSync } from "fflate";
import { createApp } from "../src/app";
import { DosyaHatasi, guvenliAd, kaydet, listele, sil, taninir } from "../src/dosyalar";

const PK = Buffer.from([0x50, 0x4b, 3, 4, 1, 2, 3, 4]);
const TOKEN = "t".repeat(40);
const SIFRE = "guclu-sifre-123";
const basic = `Basic ${Buffer.from(`admin:${SIFRE}`).toString("base64")}`;

test("guvenliAd: yol ayırıcıları atılır, tehlikeli adlar reddedilir", () => {
  assert.equal(guvenliAd("../../etc/passwd.xlsx"), "passwd.xlsx");
  assert.equal(guvenliAd("C:\\Users\\x\\fatura (1).xlsx"), "fatura (1).xlsx");
  assert.equal(guvenliAd("Şubat Fatura.xlsx"), "Şubat Fatura.xlsx");
  assert.equal(guvenliAd(".gizli.xlsx"), undefined);
  assert.equal(guvenliAd(".."), undefined);
  assert.equal(guvenliAd(""), undefined);
  assert.equal(guvenliAd("a<b>c.xlsx"), "a_b_c.xlsx");
  assert.equal(guvenliAd("x".repeat(200) + ".xlsx"), undefined);
});

test("taninir: yalnız Trendyol/Getir fatura adları", () => {
  assert.equal(taninir("prod_2026_1_SaticiFatura_9_08.10.2026-10.00.xlsx"), true);
  assert.equal(taninir("PayWithOnDelivery_Komisyon_Fatura_Detayi_v2.xlsx"), true);
  assert.equal(taninir("yemeksepeti_ekim.xlsx"), false);
});

test("kaydet: xlsx, zip içi xlsx, yanlış tür ve bozuk içerik", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "delrep-dosya-"));
  try {
    assert.deepEqual((await kaydet(dir, "A_SaticiFatura_1.XLSX", PK)).kaydedilen, ["A_SaticiFatura_1.xlsx"]); // uzantı küçülür
    await assert.rejects(kaydet(dir, "a.txt", PK), DosyaHatasi);
    await assert.rejects(kaydet(dir, "a.xlsx", Buffer.from("merhaba dunya")), DosyaHatasi);
    await assert.rejects(kaydet(dir, "a.zip", Buffer.from("PK yok")), DosyaHatasi);

    const zip = Buffer.from(
      zipSync({
        "ekim/YS_1.xlsx": new Uint8Array(PK),
        "kasim/YS_1.xlsx": new Uint8Array(PK), // aynı ad, farklı klasör: biri ötekini ezmemeli
        "__MACOSX/._YS_1.xlsx": new Uint8Array(PK),
        "okubeni.txt": new Uint8Array([1, 2, 3]),
      }),
    );
    const r = await kaydet(dir, "yemeksepeti.zip", zip);
    assert.equal(r.kaydedilen.length, 2);
    assert.equal(new Set(r.kaydedilen).size, 2);
    assert.equal(r.atlanan, 1);

    await assert.rejects(kaydet(dir, "bos.zip", Buffer.from(zipSync({ "a.txt": new Uint8Array([1, 2, 3, 4, 5]) }))), DosyaHatasi);

    const liste = await listele(dir);
    assert.equal(liste.length, 3);
    assert.equal(liste.find((f) => f.ad === "A_SaticiFatura_1.xlsx")?.taninan, true);
    assert.equal((await readdir(dir)).some((a) => a.endsWith(".tmp")), false);

    await sil(dir, "A_SaticiFatura_1.xlsx");
    assert.equal((await listele(dir)).length, 2);
    await assert.rejects(sil(dir, "../x"), DosyaHatasi);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

async function sunucu(analiz?: () => Promise<{ ok: boolean; mesaj: string }>) {
  const dir = await mkdtemp(path.join(tmpdir(), "delrep-api-"));
  const server = createApp({ dataDir: dir, uploadToken: TOKEN, viewPassword: SIFRE, analizCalistir: analiz }).listen(0);
  await new Promise((r) => server.once("listening", r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { base, kapat: async () => { server.close(); await rm(dir, { recursive: true, force: true }); } };
}

const AJAX = { "X-Requested-With": "delrep" };

test("API: kimliksiz 401, başlıksız 400, yükle-listele-sil-analiz akışı", async () => {
  let cagri = 0;
  const s = await sunucu(async () => ({ ok: ++cagri > 0, mesaj: "tamam" }));
  try {
    const ad = encodeURIComponent("Ekim SaticiFatura.xlsx");
    const put = (h: Record<string, string>) => fetch(`${s.base}/api/dosyalar/${ad}`, { method: "PUT", headers: h, body: PK });

    assert.equal((await put({ ...AJAX })).status, 401); // kimliksiz
    assert.equal((await put({ Authorization: basic })).status, 400); // X-Requested-With yok
    const ok = await put({ Authorization: basic, ...AJAX });
    assert.equal(ok.status, 200);
    assert.deepEqual((await ok.json()).kaydedilen, ["Ekim SaticiFatura.xlsx"]);

    assert.equal((await fetch(`${s.base}/api/dosyalar`)).status, 401);
    const liste = await (await fetch(`${s.base}/api/dosyalar`, { headers: { Authorization: basic } })).json();
    assert.equal(liste.dosyalar.length, 1);
    assert.equal(liste.dosyalar[0].taninan, true);

    const sayfa = await fetch(`${s.base}/yukle`, { headers: { Authorization: basic } });
    assert.equal(sayfa.status, 200);
    assert.match(sayfa.headers.get("content-security-policy") ?? "", /connect-src 'self'/);
    assert.equal((await fetch(`${s.base}/yukle`)).status, 401);

    const an = await fetch(`${s.base}/api/analiz`, { method: "POST", headers: { Authorization: basic, ...AJAX } });
    assert.equal(an.status, 200);
    assert.equal(cagri, 1);

    const sil = await fetch(`${s.base}/api/dosyalar/${ad}`, { method: "DELETE", headers: { Authorization: basic, ...AJAX } });
    assert.equal(sil.status, 200);
    assert.equal((await (await fetch(`${s.base}/api/dosyalar`, { headers: { Authorization: basic } })).json()).dosyalar.length, 0);
  } finally {
    await s.kapat();
  }
});

test("API: bozuk dosya 400, analiz yapılandırılmamışsa 501, analiz başarısızsa 422", async () => {
  const s = await sunucu();
  try {
    const kotu = await fetch(`${s.base}/api/dosyalar/a.xlsx`, { method: "PUT", headers: { Authorization: basic, ...AJAX }, body: "merhaba" });
    assert.equal(kotu.status, 400);
    const an = await fetch(`${s.base}/api/analiz`, { method: "POST", headers: { Authorization: basic, ...AJAX } });
    assert.equal(an.status, 501);
  } finally {
    await s.kapat();
  }
  const f = await sunucu(async () => ({ ok: false, mesaj: "yok" }));
  try {
    const an = await fetch(`${f.base}/api/analiz`, { method: "POST", headers: { Authorization: basic, ...AJAX } });
    assert.equal(an.status, 422);
    assert.equal((await an.json()).ok, false);
  } finally {
    await f.kapat();
  }
});
