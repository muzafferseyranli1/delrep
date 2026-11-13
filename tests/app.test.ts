import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { RAPOR_CSP, basicValid, createApp, reportFile, tokenValid } from "../src/app";

const TOKEN = "t".repeat(40);
const SIFRE = "guclu-sifre-123";
const HTML = "<!doctype html><html><body>rapor</body></html>";
const basic = (u: string, p: string) => `Basic ${Buffer.from(`${u}:${p}`).toString("base64")}`;

test("jeton: doğru jeton geçer, kısa/yanlış/eksik jeton geçmez", () => {
  assert.equal(tokenValid(TOKEN, `Bearer ${TOKEN}`), true);
  assert.equal(tokenValid(TOKEN, `Bearer ${TOKEN}x`), false);
  assert.equal(tokenValid(TOKEN, TOKEN), false);
  assert.equal(tokenValid(TOKEN, undefined), false);
  assert.equal(tokenValid("kisa", "Bearer kisa"), false);
  assert.equal(tokenValid(undefined, `Bearer ${TOKEN}`), false);
});

test("basic: doğru kullanıcı/şifre geçer, diğerleri geçmez", () => {
  assert.equal(basicValid("admin", SIFRE, basic("admin", SIFRE)), true);
  assert.equal(basicValid("admin", SIFRE, basic("admin", "yanlis")), false);
  assert.equal(basicValid("admin", SIFRE, basic("baska", SIFRE)), false);
  assert.equal(basicValid("admin", SIFRE, undefined), false);
  assert.equal(basicValid("admin", SIFRE, "Basic !!!"), false);
  assert.equal(basicValid("admin", "kisa", basic("admin", "kisa")), false); // 12 karakterden kısa şifre kabul edilmez
  assert.equal(basicValid("admin", undefined, basic("admin", SIFRE)), false);
  // şifrede ':' olabilir
  assert.equal(basicValid("admin", "a:b:c-uzun-sifre", basic("admin", "a:b:c-uzun-sifre")), true);
});

async function sunucu(opts: { uploadToken?: string; viewPassword?: string }) {
  const dir = await mkdtemp(path.join(tmpdir(), "delrep-"));
  const server = createApp({ dataDir: dir, ...opts }).listen(0);
  await new Promise((r) => server.once("listening", r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { dir, base, kapat: async () => { server.close(); await rm(dir, { recursive: true, force: true }); } };
}

const yukle = (base: string, body: string, auth?: string) =>
  fetch(`${base}/api/paketrapor`, { method: "PUT", headers: { "Content-Type": "text/html", ...(auth ? { Authorization: auth } : {}) }, body });

test("sağlık ucu kimliksiz açık", async () => {
  const s = await sunucu({});
  try {
    const r = await fetch(`${s.base}/health`);
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), { ok: true });
  } finally {
    await s.kapat();
  }
});

test("yükleme: jetonsuz 401, yanlış içerik 400, doğru yükleme dosyaya yazılır ve şifreyle sunulur", async () => {
  const s = await sunucu({ uploadToken: TOKEN, viewPassword: SIFRE });
  try {
    const giris = { headers: { Authorization: basic("admin", SIFRE) } };
    assert.equal((await fetch(`${s.base}/`, giris)).status, 404); // henüz rapor yok
    assert.equal((await yukle(s.base, HTML)).status, 401);
    assert.equal((await yukle(s.base, HTML, "Bearer yanlis")).status, 401);
    assert.equal((await yukle(s.base, "merhaba", `Bearer ${TOKEN}`)).status, 400);
    const ok = await yukle(s.base, HTML, `Bearer ${TOKEN}`);
    assert.equal(ok.status, 200);
    assert.equal(await readFile(reportFile(s.dir), "utf8"), HTML);
    for (const yol of ["/", "/paketrapor"]) {
      const sayfa = await fetch(`${s.base}${yol}`, giris);
      assert.equal(sayfa.status, 200);
      assert.equal(await sayfa.text(), HTML);
      assert.equal(sayfa.headers.get("content-security-policy"), RAPOR_CSP);
      assert.equal(sayfa.headers.get("cache-control"), "no-store");
    }
  } finally {
    await s.kapat();
  }
});

test("şifresiz sayfa 401 ve giriş penceresi ister, yanlış şifre de 401", async () => {
  const s = await sunucu({ uploadToken: TOKEN, viewPassword: SIFRE });
  try {
    await yukle(s.base, HTML, `Bearer ${TOKEN}`);
    const r = await fetch(`${s.base}/`);
    assert.equal(r.status, 401);
    assert.match(r.headers.get("www-authenticate") ?? "", /^Basic/);
    assert.equal((await fetch(`${s.base}/`, { headers: { Authorization: basic("admin", "yanlis-sifre-12") } })).status, 401);
    assert.doesNotMatch(await (await fetch(`${s.base}/`)).text(), /rapor/); // rapor içeriği sızmaz
  } finally {
    await s.kapat();
  }
});

test("jeton tanımlı değilse yükleme kapalı (503), şifre tanımlı değilse sayfa kapalı (503)", async () => {
  const s = await sunucu({});
  try {
    assert.equal((await yukle(s.base, HTML, `Bearer ${TOKEN}`)).status, 503);
    assert.equal((await fetch(`${s.base}/`, { headers: { Authorization: basic("admin", SIFRE) } })).status, 503);
  } finally {
    await s.kapat();
  }
});

test("art arda hatalı denemeden sonra 429", async () => {
  const s = await sunucu({ uploadToken: TOKEN, viewPassword: SIFRE });
  try {
    for (let i = 0; i < 10; i++) assert.equal((await yukle(s.base, HTML, "Bearer yanlis")).status, 401);
    assert.equal((await yukle(s.base, HTML, "Bearer yanlis")).status, 429);
    assert.equal((await yukle(s.base, HTML, `Bearer ${TOKEN}`)).status, 429); // doğru jeton da engelin içinde bekler
  } finally {
    await s.kapat();
  }
});
