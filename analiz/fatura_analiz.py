"""
Yerinde Pide – paket servis platform fatura analizi (referans uygulama)

Kaynak: Trendyol Go / GetirYemek (Uber Eats) satıcı panelinden indirilen iki tür Excel:
  1) prod_<yıl>_<satıcıId>_SaticiFatura_<faturaNo>_<tarih>.xlsx   -> online ödemeli siparişler (haftalık)
  2) PayWithOnDelivery_Komisyon_Fatura_Detayi_v<no>.xlsx            -> kapıda ödemeli siparişler

Kullanım:
  python fatura_analiz.py <girdi_klasoru> <cikti_klasoru>

Çıktı: ozet, akis, platform, donem, gunluk, saat, haftagunu, urun, kampanya CSV'leri.
Ekim 2026 verisiyle beklenen kontrol değerleri DEVIR_NOTU.md içinde.
"""
import glob
import os
import sys

import pandas as pd

NUM_ONLINE = ["Trendyol Hakediş", "Satıcı Hakediş", "Toplam Tutar", "Komisyon Oranı"]
NUM_KAPIDA = NUM_ONLINE + ["Satıcı İndirim", "Satici Kupon", "TGO İndirim", "TGO Kupon"]
PLATFORM_ADI = {"GetirYemek by Uber Eats": "GetirYemek", "Uber Eats TrendyolGo": "Trendyol Go"}


def _oku(dosyalar, sayisal):
    parcalar = []
    for f in dosyalar:
        d = pd.read_excel(f, dtype=str)            # hepsini metin oku, sonra çevir
        d = d.dropna(subset=["Kayıt No"])           # dosya sonundaki boş satırlar
        d["dosya"] = os.path.basename(f)
        parcalar.append(d)
    if not parcalar:
        return pd.DataFrame()
    d = pd.concat(parcalar, ignore_index=True)
    d = d.drop_duplicates(subset=["Kayıt No"])      # aynı fatura iki kez yüklenirse
    for c in sayisal:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["tarih"] = pd.to_datetime(d["Sipariş Tarihi"], format="%d.%m.%Y %H:%M")
    return d


def yukle(klasor):
    online = _oku(sorted(glob.glob(os.path.join(klasor, "*SaticiFatura*.xlsx"))), NUM_ONLINE)
    kapida = _oku(sorted(glob.glob(os.path.join(klasor, "*PayWithOnDelivery*.xlsx"))), NUM_KAPIDA)
    return online, kapida


def siparis_tablosu(online, kapida):
    """Her satır = 1 sipariş. brut, ind (indirim, pozitif), iade, net, ty (komisyon), sh (hakediş)."""
    parcalar = []
    if len(online):
        o = online.copy()
        tip = o["İşlem Tipi"]
        o["brut"] = o["Toplam Tutar"].where(tip == "Satış", 0)
        o["ind"] = -o["Toplam Tutar"].where(tip == "İndirim", 0)
        o["iade"] = -o["Toplam Tutar"].where(tip == "Kısmi İade", 0)
        g = o.groupby("Sipariş No").agg(
            app=("Uygulama Adı", "first"), t=("tarih", "first"),
            brut=("brut", "sum"), ind=("ind", "sum"), iade=("iade", "sum"),
            net=("Toplam Tutar", "sum"), ty=("Trendyol Hakediş", "sum"), sh=("Satıcı Hakediş", "sum"),
        ).reset_index()
        g["odeme"] = "Online"
        parcalar.append(g)
    if len(kapida):
        k = kapida.copy()
        k["ind"] = -k["Satıcı İndirim"]             # kapıda dosyasında indirim ayrı sütunda, satır içinde
        g = k.groupby("Sipariş No").agg(
            app=("Uygulama Adı", "first"), t=("tarih", "first"),
            brut=("Toplam Tutar", "sum"), ind=("ind", "sum"),
            ty=("Trendyol Hakediş", "sum"), sh=("Satıcı Hakediş", "sum"), odeme=("Ödeme Tipi", "first"),
        ).reset_index()
        g["iade"] = 0.0
        g["net"] = g["brut"] - g["ind"]
        parcalar.append(g)
    A = pd.concat(parcalar, ignore_index=True)
    A["platform"] = A["app"].map(PLATFORM_ADI).fillna(A["app"])
    return A


def kampanyalar(online):
    ind = online[online["İşlem Tipi"] == "İndirim"].copy()
    # Ürün Adı örneği: "Kaşarlı Pide (Açık) - (500 TL'ye 150 TL İndirim - 150.00₺)"
    ind["kampanya"] = (ind["Ürün Adı"].str.extract(r"- \((.*?) - [\d\.]+₺\)$")[0]
                       .str.replace("’", "'", regex=False))
    s = ind.groupby(["Sipariş No", "kampanya"]).agg(t=("tarih", "first"), tut=("Toplam Tutar", "sum")).reset_index()
    c = s.groupby("kampanya").agg(
        siparis=("tut", "size"), toplam_indirim=("tut", lambda x: -x.sum()),
        ort_indirim=("tut", lambda x: -x.mean()), ilk=("t", "min"), son=("t", "max"),
    ).reset_index().sort_values("toplam_indirim", ascending=False)
    c["ilk"] = c["ilk"].dt.strftime("%d.%m.%Y")
    c["son"] = c["son"].dt.strftime("%d.%m.%Y")
    return c.round(2)


def urunler(online, kapida, ilk_n=15):
    s = pd.concat([online[online["İşlem Tipi"] == "Satış"][["Ürün Adı", "Toplam Tutar"]],
                   kapida[["Ürün Adı", "Toplam Tutar"]] if len(kapida) else None])
    p = (s.groupby("Ürün Adı").agg(kalem=("Toplam Tutar", "size"), ciro=("Toplam Tutar", "sum"),
                                   medyan_fiyat=("Toplam Tutar", "median"))
         .sort_values("ciro", ascending=False).reset_index().rename(columns={"Ürün Adı": "urun"}))
    p["pay"] = p["ciro"] / p["ciro"].sum() * 100
    ust, kalan = p.head(ilk_n), p.iloc[ilk_n:]
    if len(kalan):
        ust = pd.concat([ust, pd.DataFrame([dict(urun=f"Diğer ({len(kalan)} ürün)", kalem=kalan.kalem.sum(),
                                                 ciro=kalan.ciro.sum(), medyan_fiyat=None, pay=kalan.pay.sum())])])
    return ust.round(2)


def donemler(A, sinirlar):
    """sinirlar: [(etiket, 'YYYY-MM-DD', 'YYYY-MM-DD'), ...] – farklı uzunluktaki dönemler günlüğe çevrilir."""
    rows = []
    for ad, a, b in sinirlar:
        bas, bit = pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(days=1)
        s = A[(A.t >= bas) & (A.t < bit)]
        n = (bit - bas).days
        if not len(s):
            continue
        rows.append(dict(donem=ad, gun=n, siparis=len(s), gunluk_siparis=len(s) / n,
                         gunluk_brut=s.brut.sum() / n, indirim_orani=s.ind.sum() / s.brut.sum() * 100,
                         gunluk_hakedis=s.sh.sum() / n, ort_sepet=s.brut.mean()))
    return pd.DataFrame(rows).round(2)


def analiz(klasor, cikti, donem_sinirlari=None):
    online, kapida = yukle(klasor)
    A = siparis_tablosu(online, kapida)
    os.makedirs(cikti, exist_ok=True)
    T = A[["brut", "ind", "iade", "net", "ty", "sh"]].sum()

    pd.DataFrame([dict(
        siparis=len(A), brut=T.brut, indirim=T.ind, iade=T.iade, net=T.net, komisyon=T.ty, hakedis=T.sh,
        ort_sepet=A.brut.mean(), indirim_orani=T.ind / T.brut * 100, komisyon_brut_orani=T.ty / T.brut * 100,
        kesinti_orani=(T.ind + T.ty + T.iade) / T.brut * 100, hakedis_orani=T.sh / T.brut * 100,
        indirimli_siparis_orani=(A.ind > 0.01).mean() * 100, kapida_siparis=int((A.odeme != "Online").sum()),
    )]).round(2).to_csv(f"{cikti}/ozet.csv", index=False)

    pd.DataFrame([dict(adim="Brüt satış", tutar=T.brut), dict(adim="İndirimler", tutar=-T.ind),
                  dict(adim="İade", tutar=-T.iade), dict(adim="Komisyon", tutar=-T.ty),
                  dict(adim="Satıcı hakedişi", tutar=T.sh)]).round(2).to_csv(f"{cikti}/akis.csv", index=False)

    g = A.groupby("platform").agg(siparis=("brut", "size"), brut=("brut", "sum"), indirim=("ind", "sum"),
                                  komisyon=("ty", "sum"), hakedis=("sh", "sum"),
                                  indirimli_siparis_orani=("ind", lambda s: (s > .01).mean() * 100)).reset_index()
    g["ort_sepet"] = g.brut / g.siparis
    g["indirim_orani"] = g.indirim / g.brut * 100
    g["hakedis_orani"] = g.hakedis / g.brut * 100
    g["siparis_basi_hakedis"] = g.hakedis / g.siparis
    g.round(2).to_csv(f"{cikti}/platform.csv", index=False)

    if donem_sinirlari:
        donemler(A, donem_sinirlari).to_csv(f"{cikti}/donem.csv", index=False)

    A["gun"] = A.t.dt.strftime("%Y-%m-%d")
    (A.groupby("gun").agg(siparis=("brut", "size"), brut=("brut", "sum"), indirim=("ind", "sum"), hakedis=("sh", "sum"))
     .round(2).reset_index().to_csv(f"{cikti}/gunluk.csv", index=False))

    A["saat"] = A.t.dt.hour
    h = A.groupby("saat").agg(siparis=("brut", "size"), brut=("brut", "sum")).round(2).reset_index()
    h["saat_etiket"] = h.saat.map(lambda x: f"{x:02d}:00")
    h.to_csv(f"{cikti}/saat.csv", index=False)

    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    A["dow"] = A.t.dt.dayofweek
    x = A.groupby("dow").agg(siparis=("brut", "size"), brut=("brut", "sum"), gun_sayisi=("gun", "nunique")).reset_index()
    x["gun_adi"] = x.dow.map(lambda i: gunler[i])
    x["gunluk_siparis"] = (x.siparis / x.gun_sayisi).round(1)   # gün sayısına böl, ham toplam yanıltır
    x["gunluk_brut"] = (x.brut / x.gun_sayisi).round(0)
    x[["dow", "gun_adi", "gun_sayisi", "siparis", "gunluk_siparis", "gunluk_brut"]].to_csv(f"{cikti}/haftagunu.csv", index=False)

    urunler(online, kapida).to_csv(f"{cikti}/urun.csv", index=False)
    kampanyalar(online).to_csv(f"{cikti}/kampanya.csv", index=False)
    A.drop(columns=["dow"]).to_csv(f"{cikti}/siparisler.csv", index=False)   # sipariş bazlı ham tablo
    return A


if __name__ == "__main__":
    ekim = [("1–4 Eki", "2026-10-01", "2026-10-04"), ("5–11 Eki", "2026-10-05", "2026-10-11"),
            ("12–18 Eki", "2026-10-12", "2026-10-18"), ("19–25 Eki", "2026-10-19", "2026-10-25"),
            ("26–31 Eki", "2026-10-26", "2026-10-31")]
    A = analiz(sys.argv[1], sys.argv[2], ekim)
    print(f"{len(A)} sipariş, brüt {A.brut.sum():,.2f}, hakediş {A.sh.sum():,.2f}")
