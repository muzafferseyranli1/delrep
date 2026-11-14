# delrep: paket servis raporu

Paket servis platformlarının fatura Excel'lerini web sayfasından yüklersiniz; sunucu faturaları biriktirir, analiz eder ve raporu şifreyle gösterir. Hangi bilgisayardan girerseniz girin aynı veriyi görürsünüz.

**Akış:** `/yukle` sayfasında dosyalar yüklenir → `/data/faturalar` altında birikir → `analiz/calistir.py` hepsini baştan işler → `/` adresinde HTML rapor görünür.

**Analiz motoru (`analiz/`):** `okuma.py` dosyaları adından değil içeriğinden tanır (zip içleri dahil), `hesap.py` beş amacı hesaplar, `rapor.py` tek dosyalık HTML üretir. Beş amaç: fatura kontrolü, trend, müşteri algısı, kampanya etkisi, reklam etkisi. Dönemler platformların fatura dönemleridir (ayın 1–7, 8–14, 15–21, 22–28, 29–son). Mağaza dosya içeriğinden bulunur; aynı kayıt birden çok dosyada varsa en yeni dosyadaki kalır. Analizin başlangıç günü `ANALIZ_BASLANGIC` ortam değişkeniyle değiştirilebilir.

Tanınan raporlar:
- **Trendyol Go:** komisyon fatura detayı (`SaticiFatura`), kapıda ödeme detayı (`PayWithOnDelivery`), fatura listesi (`Faturalar_`), reklam raporu (`Reklam-`), değerlendirmeler.
- **Yemeksepeti (CSV):** sipariş listesi, fatura özeti, günlük performans, ürün satışları, değerlendirmeler.

Yerelde çalıştırma: `python3 -I analiz/calistir.py <girdi_klasoru> <cikti_klasoru> <rapor.html>`

> **Eksik:** web yükleme (`src/dosyalar.ts`) henüz yalnız `.xlsx` ve `.zip` kabul ediyor ve yalnız `SaticiFatura`/`PayWithOnDelivery` dosyalarını "tanınan" sayıyor. Yemeksepeti'nin `.csv` dosyaları için güncellenmeli.

| Uç | Koruma | Ne yapar |
|---|---|---|
| `GET /health` | yok | Sağlık kontrolü |
| `GET /` ve `/paketrapor` | tarayıcı giriş penceresi (`VIEW_USER` / `VIEW_PASSWORD`) | Raporu gösterir |
| `GET /yukle` | aynı | Fatura yükleme, dosya listesi, silme, raporu yeniden hesaplama |
| `GET /api/dosyalar`, `PUT /api/dosyalar/<ad>`, `DELETE /api/dosyalar/<ad>`, `POST /api/analiz` | aynı + değiştirenlerde `X-Requested-With: delrep` başlığı | `/yukle` sayfasının kullandığı uçlar (dosya en çok 100 MB) |
| `PUT /api/paketrapor` | `Authorization: Bearer <UPLOAD_TOKEN>` | Hazır HTML raporu doğrudan yükler (en çok 5 MB). Sonraki analiz bu raporun üzerine yazar |

Sayfalar sıkı CSP ile sunulur (dış kaynak yok), önbelleğe alınmaz. Hatalı jeton/şifre denemesi IP başına 15 dakikada 10 ile sınırlıdır. Faturalar finansal veridir: `/data` volume'unu yedeklemeyi ve yalnızca güvendiğiniz kişilerle şifreyi paylaşmayı unutmayın.

## Ortam değişkenleri

`.env.example` dosyasına bakın. `UPLOAD_TOKEN` en az 32, `VIEW_PASSWORD` en az 12 karakter olmalı; yoksa ilgili uç kapalı kalır (503).

## Yerelde çalıştırma

```bash
npm install
npm test                                   # Node testleri
python3 -m unittest analiz/test_analiz.py  # analiz hattı (pandas ve openpyxl gerekir)
UPLOAD_TOKEN=<32+ karakter> VIEW_PASSWORD=<12+ karakter> npm start
```

Analiz yerelde çalışacaksa Python 3, `pandas` ve `openpyxl` kurulu olmalı (`PYTHON_BIN` ile yorumlayıcı seçilebilir). Docker imajında hazırdır.

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
7. **Deploy**, sonra `https://<alan-adı>/` adresinde kullanıcı adı/şifre sorulmalı; ilk açılışta "Henüz rapor yok" görünür. Faturaları `https://<alan-adı>/yukle` adresinden yükleyin.
8. İsteğe bağlı: *Webhooks* sekmesinden GitHub push'larında otomatik deploy.
