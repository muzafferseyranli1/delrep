# delrep: paket servis raporu

Yerelde üretilen tek dosyalık HTML raporu alır, şifreyle gösterir. Küçük bir Express uygulamasıdır (veritabanı yok; rapor tek dosya olarak `DATA_DIR` içinde durur).

| Uç | Koruma | Ne yapar |
|---|---|---|
| `GET /health` | yok | Sağlık kontrolü |
| `PUT /api/paketrapor` | `Authorization: Bearer <UPLOAD_TOKEN>` | HTML raporu yükler (en çok 5 MB, `<!doctype html` ile başlamalı) |
| `GET /` ve `/paketrapor` | tarayıcı giriş penceresi (`VIEW_USER` / `VIEW_PASSWORD`) | Raporu gösterir |

Rapor sayfası sıkı CSP ile sunulur (dış kaynak yok), önbelleğe alınmaz. Hatalı jeton/şifre denemesi IP başına 15 dakikada 10 ile sınırlıdır.

## Ortam değişkenleri

`.env.example` dosyasına bakın. `UPLOAD_TOKEN` en az 32, `VIEW_PASSWORD` en az 12 karakter olmalı; yoksa ilgili uç kapalı kalır (503).

## Yerelde çalıştırma

```bash
npm install
npm test
UPLOAD_TOKEN=<32+ karakter> VIEW_PASSWORD=<12+ karakter> npm start
```

## Rapor yükleme (yerel betikten)

```bash
curl -X PUT https://<alan-adı>/api/paketrapor \
  -H "Authorization: Bearer $UPLOAD_TOKEN" \
  -H "Content-Type: text/html" \
  --data-binary @rapor.html
```

## Coolify kurulumu

1. **Yeni kaynak:** Project > Environment > *+ New* > *Public/Private Repository* (GitHub). Repo: `muzafferseyranli1/delrep`, branch `main`. Repo özelse GitHub App ya da deploy key bağlayın.
2. **Build Pack:** `Dockerfile`. Port: `3000`.
3. **Domain:** örn. `https://rapor.derinsoft.com.tr` (DNS'te A kaydı VPS IP'sine). Coolify Let's Encrypt sertifikasını kendi alır; HTTPS şart, çünkü giriş HTTP Basic.
4. **Environment Variables:** `UPLOAD_TOKEN`, `VIEW_PASSWORD`, `VIEW_USER` (isteğe bağlı), `DATA_DIR=/data`. Gizli değerlerde *Build Variable* işaretini **kapatın** (yalnızca çalışma zamanı).
5. **Persistent Storage:** *Volume* ekleyin, hedef yol `/data`. Bu olmazsa her deploy'da yüklenen rapor silinir.
6. **Health Check:** yol `/health`, port `3000` (Dockerfile'da da tanımlı).
7. **Deploy**, sonra `https://<alan-adı>/` adresinde kullanıcı adı/şifre sorulmalı; ilk açılışta "Henüz rapor yüklenmedi" görünür.
8. İsteğe bağlı: *Webhooks* sekmesinden GitHub push'larında otomatik deploy.
