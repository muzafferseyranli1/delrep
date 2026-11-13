# Devir notu: delrep (paket servis raporu) projesi

Tarih: 14 Kasım 2026. Bu not, işi devralacak ajan için yazıldı. Önce "Özet" ve "Yapılacaklar"ı okuyun.

> **Güvenlik:** Bu repo şu an GitHub'da **herkese açık**. Nota ve koda gelir/sipariş rakamı, gizli değer, sunucu IP'si ya da Coolify kimlikleri koymayın. Kullanıcıya repoyu özel (private) yapmasını önerdim; yapılırsa Coolify'da GitHub App ya da deploy key ile yeniden bağlamak gerekir.

## 1. Özet

- Amaç: paket servis raporunu (şimdilik `tndrWA` içinde `/paketrapor`) ayrı bir proje yapmak ve fatura dosyalarını **web sayfasından** yüklemek, çünkü kullanıcı hep aynı bilgisayarda çalışmıyor.
- Yapıldı: bağımsız Express uygulaması, canlıya alındı (`rapor.derinsoft.com.tr`), yükleme sayfası ve dosya birikimi yazıldı.
- **Yapılmadı / önemli:** gerçek analiz motoru bu repoda **yok**. `analiz/` altındaki kod yalnızca yer tutucudur (aşağıda 3. bölüm). Gerçek `fatura_analiz.py` ve `rapor.py` sizde (`Yrndpaket` klasörü) olmalı.
- Doğrulanmadı: bu repoyu yazdığım bilgisayarda Node ve Python yoktu. Hiçbir test çalıştırılmadı. Yükleme/analiz özelliği (aşağıda "Commit'ler") Coolify'da hiç derlenmedi.

## 2. Canlı kurulum (Coolify)

| Ne | Değer |
|---|---|
| Repo | `muzafferseyranli1/delrep`, branch `main` |
| Coolify | Proje `delrep` > production > uygulama (Public Git Repository, build pack Dockerfile, port 3000) |
| Alan adı | `rapor.derinsoft.com.tr` (DNS zaten sunucuya bağlı; Coolify `www.` sürümünü de ekledi). Otomatik `sslip.io` adresini sildim: HTTP olduğu için şifre açık giderdi |
| Kalıcı depolama | Volume, hedef yol `/data` |
| Ortam değişkenleri | `UPLOAD_TOKEN` (32+ karakter), `VIEW_PASSWORD` (12+), `VIEW_USER` (varsayılan admin), `DATA_DIR=/data`. Gizli ikisi **runtime-only** (build time kapalı) |
| Sağlık kontrolü | `GET /health` (Dockerfile'da da var) |
| Deploy | Elle. GitHub push'unda **otomatik deploy yok** (public repo, webhook kurulmadı) |

Gizli değerleri kullanıcı şifre yöneticisine kaydetti. Bunları sohbete/repoya yazmayın. Üretildikleri bilgisayarda `.env` dosyası (git'in yok saydığı) duruyor olabilir.

İlk deploy (commit `21867cc`) başarılı oldu: `/health` 200, şifresiz `/` 401, yanlış jetonla yükleme 401. Şifreyle giriş ve gerçek rapor yükleme **denenmedi**.

## 3. Repo içeriği

```
src/app.ts          Express: /health, /, /paketrapor, /yukle, /api/dosyalar, /api/analiz, PUT /api/paketrapor
src/dosyalar.ts     Fatura dosyası saklama: .xlsx doğrudan, .zip sunucuda açılır (yalnız .xlsx kalır), güvenli ad, liste, sil
src/analiz.ts       Python'u çalıştırır (execFile, 180 sn zaman aşımı, tek seferde bir analiz), raporu atomik yazar
src/yukle-sayfasi.ts /yukle sayfası (sürükle-bırak, dosya listesi, silme, "raporu yeniden hesapla")
src/index.ts        Ortam değişkenlerini okur, uygulamayı başlatır
analiz/fatura_analiz.py   ESKİ, SADE referans betik (kullanıcının Downloads'taki kopyası, değiştirilmedi)
analiz/calistir.py        fatura_analiz.py'yi çağırır, haftalık dönemleri veriden üretir, rapor.py'yi çağırır
analiz/rapor.py           BENİM yazdığım basit HTML rapor (yer tutucu; gerçek rapor.py değil)
analiz/test_analiz.py     Sentetik veriyle hat testi (çalıştırılmadı)
tests/                    Node testleri (çalıştırılmadı)
Dockerfile                node:22-alpine + python3, py3-pandas, py3-openpyxl
```

Akış: `/yukle` > dosyalar `/data/faturalar` altında birikir > `POST /api/analiz` > `python3 -I analiz/calistir.py <faturalar> <analiz-cikti> <geçici rapor>` > başarılıysa rapor `/data/index.html` olarak yer değiştirir > `/` gösterir.

Güvenlik tasarımı: HTTP Basic (yalnız HTTPS arkasında), hatalı jeton/şifre için IP başına 15 dk'da 10 deneme sınırı, rapor ve yükleme sayfası sıkı CSP ile sunulur (dış kaynak yok; satır içi stil/betik serbest), değiştiren uçlarda `X-Requested-With: delrep` zorunlu (çapraz site isteği ön kontrolde elenir), dosya adı temizlenir, zip girişi/boyutu sınırlı (500 dosya, dosya başı 100 MB, toplam 300 MB).

## 4. Kritik bulgu: gerçek rapor çok daha kapsamlı

Canlıdaki mevcut rapor (`tndrwa` uygulamasının `/data/paketrapor/index.html` dosyası, ~140 KB, 12 Kasım'da yüklenmiş) şunları içeriyor ve `analiz/` altındaki yer tutucu **bunların çoğunu yapmıyor**:

- İki mağaza (Yerinde Pide, Yerinde Tandır), mağaza karşılaştırması, sekmeli sayfa.
- İki platform: Trendyol Go ve Yemeksepeti (Yemeksepeti haftalık dökümleri, KDV ve stopaj mantığı, siparişte saat/ürün olmaması).
- Reklam analizi (tekil reklam günü etkisi, sürekli reklam dönemi, başa baş), ISO hafta eğilimleri, ay ay karşılaştırma, ürün ve kampanya tabloları, saat/haftagünü grafikleri.
- Fatura mutabakatı: komisyon faturaları sipariş dosyalarıyla kuruşu kuruşuna karşılaştırılıyor.
- Girdi: Trendyol online ve kapıda sipariş dosyaları, `Faturalar_*.xlsx` fatura listeleri (mağazayı bunlardan buluyor), Yemeksepeti dökümleri.

Bu raporu üreten gerçek betikler kodun yorumuna göre `Yrndpaket: fatura_analiz.py + rapor.py`. Devir notundaki (kullanıcının `DEVIR_NOTU.md` dosyası) Ekim kontrol değerleri de eskimiş; **doğrulama için canlıdaki mevcut raporu kaynak alın**. O rakamları bu repoya yazmayın (repo public).

## 5. Yapılacaklar (sırayla)

1. **Gerçek betikleri taşıyın:** `Yrndpaket` klasöründeki `fatura_analiz.py` ve `rapor.py` (ve yardımcı dosyalar) `analiz/` altına. Yer tutucuları (`rapor.py`, `calistir.py`) onlara göre değiştirin; `calistir.py` onların komut satırı/klasör düzenine uyarlansın. Rapor çıktısı yine tek dosyalık HTML olmalı ve CSP'ye uymalı (`src/app.ts` içindeki `RAPOR_CSP`: dış kaynak yok, satır içi stil/betik ve `data:` görsel serbest; tndrWA'daki CSP aynısı, gerçek rapor sorunsuz çalışmalı).
2. **Yemeksepeti zip'ini gerçek dosyayla deneyin:** `src/dosyalar.ts` zip içinden yalnız `.xlsx` saklıyor, diğerlerini atlıyor, ve `taninir()` yalnız `SaticiFatura`/`PayWithOnDelivery` adlı dosyaları "tanınan" sayıyor. Yemeksepeti dökümlerinin dosya türü/adı ve `Faturalar_*.xlsx` adları buna uymuyorsa `kaydet`, `taninir` ve testleri güncelleyin.
3. **Bağımlılıklar ve süre:** Gerçek betikler `pandas/openpyxl` dışında paket istiyorsa `Dockerfile`'a ekleyin (Alpine: `apk add py3-...`). Analiz 180 sn'den uzun sürerse `src/analiz.ts` içindeki `ZAMAN_ASIMI_MS`'i artırın; gerekirse arayüzde iş durumunu yoklayan bir yapıya geçin.
4. **Test edin:** Node ve Python'lu bir makinede `npm install`, `npm test`, `python3 -m unittest analiz/test_analiz.py`. `package-lock.json` yok: `npm install` sonrası commit edin. Ardından Coolify'da deploy edin, gerçek faturaları `/yukle`'den yükleyin ve çıkan raporu canlıdaki mevcut raporla sayı sayı karşılaştırın.
5. **Ancak 4 tamamsa `tndrWA`'dan ayırın** (silmeden önce kullanıcıdan onay alın, üretim verisi):
   - `server/routes/paketrapor.ts`, `tests/paketrapor.test.ts`
   - `server/index.ts` içindeki `paketRaporUploadRouter` / `paketRaporPageRouter` import ve bağlama satırları (ve `paketRaporDir` tanımı)
   - `.env.example` içindeki `PAKETRAPOR_TOKEN` bloğu, `.gitignore`'a o commit'te eklenen satırlar (`git show 7d4d3f0`)
   - Coolify `tndrwa` uygulamasında varsa `PAKETRAPOR_TOKEN` ortam değişkeni
   - `/data/paketrapor/` klasörü (sunucuda tndrwa volume'unda): silmeden önce yeni sitede eşdeğer rapor olduğundan emin olun
   - Yerel yükleme betiğindeki adres/jeton (artık `rapor.derinsoft.com.tr` ve yeni `UPLOAD_TOKEN`)
   - İsteğe bağlı: eski `tndrwa.../paketrapor` adresini yeni siteye yönlendirin.
6. `README.md` ve bu notu güncel tutun.

## 6. Bilinmesi gerekenler

- Yazılan kod `tndrWA` içindeki `/paketrapor` kodundan türetildi; oturum çerezi yerine HTTP Basic kullanıyor (ayrı proje, panel girişi yok).
- Eski `PUT /api/paketrapor` ucu duruyor: hazır HTML'i doğrudan yükler. Sonraki analiz o dosyanın üzerine yazar.
- Coolify'da `tndrwa` konteynerinin terminali çalışıyor (veri `/data` volume'unda; `find -xdev` o volume'u atlar). Orada Excel/zip yok; yalnız hazır rapor var.
- Coolify'da gizli değişkenlerde "Build time" açık gelir; kapatın (`UPLOAD_TOKEN`, `VIEW_PASSWORD` için yaptım).
- `localhost` sunucusunda Coolify "Attention required" uyarısı var; bu projeyle ilgili olmayabilir, dokunmadım.
- Git kimliği: kullanıcının adı/e-postası kullanıldı; commit'ler `Co-Authored-By` satırı taşıyor.

## 7. Commit'ler

- `21867cc` Bağımsız Express uygulaması (jetonla HTML yükleme, Basic ile gösterme, Dockerfile). **Canlıya alındı.**
- Sonraki commit: web'den fatura yükleme (zip açma, birikim, Python analiz çalıştırıcı, yer tutucu rapor). **Henüz deploy edilmedi, hiç derlenmedi.**
