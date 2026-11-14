import assert from "node:assert/strict";
import { mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { zipSync } from "fflate";
import { createApp } from "../src/app";
import { DosyaHatasi, guvenliAd, kaydet, listele, sil } from "../src/dosyalar";

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

const metin = (s: string) => new Uint8Array(Buffer.from(s, "utf8"));

test("kaydet: xlsx, csv, zip içi dosyalar, yanlış tür ve bozuk içerik", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "delrep-dosya-"));
  try {
    assert.deepEqual((await kaydet(dir, "A_SaticiFatura_1.XLSX", PK)).kaydedilen, ["A_SaticiFatura_1.xlsx"]); // uzantı küçülür
    assert.deepEqual((await kaydet(dir, "siparisler.CSV", Buffer.from("Sipariş No,Ara Toplam\n1,\"1.000,00\"\n"))).kaydedilen, ["siparisler.csv"]);
    await assert.rejects(kaydet(dir, "a.txt", PK), DosyaHatasi);
    await assert.rejects(kaydet(dir, "a.xlsx", Buffer.from("merhaba dunya")), DosyaHatasi);
    await assert.rejects(kaydet(dir, "a.csv", Buffer.from([0x50, 0x4b, 0, 0, 1])), DosyaHatasi); // ikili içerik csv değildir
    await assert.rejects(kaydet(dir, "a.csv", Buffer.alloc(0)), DosyaHatasi);
    await assert.rejects(kaydet(dir, "a.zip", Buffer.from("PK yok")), DosyaHatasi);

    const zip = Buffer.from(
      zipSync({
        "ekim/YS_1.csv": metin("a,b\n1,2\n"),
        "kasim/YS_1.csv": metin("a,b\n3,4\n"), // aynı ad, farklı içerik: biri ötekini ezmemeli
        "kasim/fatura.xlsx": new Uint8Array(PK), // daha önce yüklenen dosyanın aynısı
        "__MACOSX/._YS_1.csv": metin("x"),
        "okubeni.txt": new Uint8Array([1, 2, 3]),
      }),
    );
    const r = await kaydet(dir, "yemeksepeti.zip", zip);
    assert.deepEqual(r.kaydedilen.sort(), ["YS_1 (2).csv", "YS_1.csv"]);
    assert.deepEqual(r.zatenVar, ["A_SaticiFatura_1.xlsx"]);
    assert.equal(r.atlanan, 1);

    // aynı dosya ikinci kez: saklanmaz; aynı ad farklı içerik: sayı eklenir
    assert.deepEqual(await kaydet(dir, "siparisler.csv", Buffer.from("Sipariş No,Ara Toplam\n1,\"1.000,00\"\n")),
      { kaydedilen: [], zatenVar: ["siparisler.csv"], atlanan: 0 });
    assert.deepEqual((await kaydet(dir, "siparisler.csv", Buffer.from("Sipariş No\n2\n"))).kaydedilen, ["siparisler (2).csv"]);

    await assert.rejects(kaydet(dir, "bos.zip", Buffer.from(zipSync({ "a.txt": new Uint8Array([1, 2, 3, 4, 5]) }))), DosyaHatasi);

    const liste = await listele(dir);
    assert.equal(liste.length, 5);
    assert.equal(liste[0].durum, null); // analiz özeti yoksa tür/durum bilinmez
    assert.equal((await readdir(dir)).some((a) => a.endsWith(".tmp")), false);

    const ozetYolu = path.join(dir, "..", `${path.basename(dir)}-ozet.json`);
    await writeFile(ozetYolu, JSON.stringify({ dosyalar: [
      { ad: "siparisler.csv", tur: "Yemeksepeti sipariş listesi", satir: 1, durum: "okundu" },
      { ad: "YS_1.csv", tur: "", satir: 0, durum: "tanınmadı (sütunlar bilinen bir rapora uymuyor)" },
    ] }));
    try {
      const l2 = await listele(dir, ozetYolu);
      assert.deepEqual(l2.find((f) => f.ad === "siparisler.csv"), { ...l2.find((f) => f.ad === "siparisler.csv")!, tur: "Yemeksepeti sipariş listesi", durum: "okundu" });
      assert.equal(l2.find((f) => f.ad === "YS_1.csv")?.tur, null);
      assert.match(l2.find((f) => f.ad === "YS_1.csv")?.durum ?? "", /tanınmadı/);
    } finally {
      await rm(ozetYolu, { force: true });
    }

    await sil(dir, "A_SaticiFatura_1.xlsx");
    assert.equal((await listele(dir)).length, 4);
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
    assert.equal(liste.dosyalar[0].durum, null); // henüz analiz edilmedi

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
