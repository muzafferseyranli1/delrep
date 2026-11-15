"""Paket servis analizinin hesapları.

Beş amaç: fatura kontrolü, trend, müşteri algısı, kampanya etkisi, reklam etkisi.
Reklam (platformda öne çıkmak için ödenen bedel) ile kampanya (indirim/kupon) ayrı tutulur.

Dönemler platformların fatura dönemleridir: ayın 1–7, 8–14, 15–21, 22–28 ve 29–son günü.
İki platform da bu dönemlerle faturalıyor; dönemler aylara tam oturur.

Tutarlar KDV dahil karşılaştırılır: Trendyol hakedişi zaten KDV dahil; Yemeksepeti komisyonu ve
reklam ücretleri KDV hariç geldiği için %20 eklenir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from okuma import Girdi, sayilar, tarih_iso, tarih_tr

TY, YS = "Trendyol Go", "Yemeksepeti"
KDV = 0.20
AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
AY_UZUN = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
DUSUK_PUAN = 3.0  # bu puan ve altı "düşük" sayılır


# ---------------------------------------------------------------- dönemler

def donem_bas(d: date) -> date:
    return d.replace(day=1 if d.day <= 7 else 8 if d.day <= 14 else 15 if d.day <= 21 else 22 if d.day <= 28 else 29)


def donem_bit(b: date) -> date:
    if b.day == 29:
        return (b.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return b + timedelta(days=6)


def donemler(bas: date, son: date) -> list[tuple[date, date]]:
    out, d = [], donem_bas(bas)
    while d <= son:
        b = donem_bit(d)
        out.append((max(d, bas), min(b, son)))
        d = b + timedelta(days=1)
    return out


def etiket(b: date, s: date) -> str:
    if b.month == s.month:
        return f"{b.day}–{s.day} {AY[b.month - 1]}" if b != s else f"{b.day} {AY[b.month - 1]}"
    return f"{b.day} {AY[b.month - 1]} – {s.day} {AY[s.month - 1]}"


def _ad(x) -> str:
    return re.sub(r"\s+", " ", str(x)).strip()


def _no(seri: pd.Series) -> pd.Series:
    return seri.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def _tirnak(x: str) -> str:
    return re.sub(r"\s+", " ", x.replace("’", "'").replace("‘", "'")).strip()


KAMPANYA_RE = re.compile(r" - \((.+) - [\d.,]+\s*₺\)\s*$")


def ty_kampanya_adi(urun: str) -> str:
    m = KAMPANYA_RE.search(str(urun))
    return _tirnak(m.group(1)) if m else "(adı yok)"


def reklam_kodu_zamani(kod: str, ilk_gun: date) -> datetime | None:
    """'12091428' → 12.09 14:28. Yıl, kampanyanın ilk raporlanan gününden alınır."""
    m = re.match(r"(\d{2})(\d{2})(\d{2})(\d{2})", kod)
    if not m:
        return None
    gun, ay, sa, dk = map(int, m.groups())
    try:
        t = datetime(ilk_gun.year, ay, gun, sa, dk)
        if t.date() > ilk_gun + timedelta(days=1):
            t = t.replace(year=ilk_gun.year - 1)
        return t
    except ValueError:
        return None


def _mod(seri: pd.Series):
    s = seri.dropna()
    return s.mode().iloc[0] if len(s) else np.nan


# ---------------------------------------------------------------- model

@dataclass
class Uyari:
    magaza: str
    seviye: str  # "hata" | "uyari" | "bilgi"
    metin: str


@dataclass
class Analiz:
    bas: date
    son: date
    donemler: list
    magazalar: list
    siparis: pd.DataFrame
    kampanya: pd.DataFrame
    ty_dosya: pd.DataFrame
    ty_satir_sapma: pd.DataFrame
    ty_fatura: pd.DataFrame
    ty_reklam: pd.DataFrame
    ty_reklam_kampanya: pd.DataFrame
    ty_deg: pd.DataFrame
    ys_fatura: pd.DataFrame
    ys_sapma: pd.DataFrame
    ys_perf: pd.DataFrame
    ys_deg: pd.DataFrame
    kapsam: dict
    uyarilar: list = field(default_factory=list)
    urun: pd.DataFrame = field(default_factory=pd.DataFrame)  # platform, magaza, gun, urun, adet, ciro
    magaza_no: dict = field(default_factory=dict)  # mağaza adı -> {platform: numara}


BOS = pd.DataFrame()


def _en_yeni(df: pd.DataFrame, anahtar: list) -> pd.DataFrame:
    return df.sort_values("_zaman", kind="stable").drop_duplicates(anahtar, keep="last")


# ---- Trendyol sipariş satırları

def _ty_satirlar(g: Girdi) -> pd.DataFrame:
    parcalar = []
    for tur in ("ty_online", "ty_kapida"):
        df = g.tablolar.get(tur)
        if df is None:
            continue
        d = pd.DataFrame({
            "tur": tur,
            "kayit": _no(df["Kayıt No"]),
            "tip": df["İşlem Tipi"].astype(str).str.strip(),
            "siparis": _no(df["Sipariş No"]),
            "zaman": tarih_tr(df["Sipariş Tarihi"]),
            "islem": tarih_tr(df["İşlem Tarihi"]),
            "urun": df["Ürün Adı"].astype(str),
            "oran": sayilar(df["Komisyon Oranı"]),
            "tutar": sayilar(df["Toplam Tutar"]),
            "ty_hak": sayilar(df["Trendyol Hakediş"]),
            "satici_hak": sayilar(df["Satıcı Hakediş"]),
            "uygulama": df["Uygulama Adı"].astype(str).str.strip(),
            "magaza_no": _no(df["Mağaza No'su"]),
            "magaza": df["Mağaza Adı"].map(_ad),
            "_dosya": df["_dosya"], "_zaman": df["_zaman"], "_sha": df["_sha"],
        })
        if tur == "ty_kapida":
            d["s_ind"] = sayilar(df["Satıcı İndirim"])
            d["s_kup"] = sayilar(df["Satici Kupon"])
            d["p_ind"] = sayilar(df["TGO İndirim"]) + sayilar(df["TGO Kupon"])
            d["odeme"] = "Kapıda"
        else:
            d["s_ind"] = d["s_kup"] = d["p_ind"] = 0.0
            d["odeme"] = "Online"
        parcalar.append(d)
    if not parcalar:
        return BOS
    return pd.concat(parcalar, ignore_index=True)


def _ty_dosya_ozeti(s: pd.DataFrame) -> pd.DataFrame:
    """Her detay dosyası bir faturaya karşılık gelir: dosya toplamı = fatura tutarı."""
    if s.empty:
        return BOS
    s = s.assign(donem=s["islem"].fillna(s["zaman"]).dt.date.map(donem_bas))
    g = s.groupby("_sha").agg(dosya=("_dosya", "first"), tur=("tur", "first"), magaza=("magaza", "first"),
                              donem=("donem", _mod), ilk=("zaman", "min"), son=("zaman", "max"),
                              tutar=("ty_hak", "sum"), satir=("kayit", "size"), dosya_zamani=("_zaman", "max"),
                              anahtar=("kayit", lambda x: "|".join(sorted(x)))).reset_index()
    # Aynı fatura yeniden indirilince bayt bayt farklı ama kayıtları aynı bir dosya gelebilir: en yenisi kalır
    g = g.sort_values("dosya_zamani").drop_duplicates(["tur", "anahtar"], keep="last").drop(columns=["anahtar"])
    g["tutar"] = g["tutar"].round(2)
    return g.reset_index(drop=True)


def _ty_satir_sapmalari(s: pd.DataFrame) -> pd.DataFrame:
    """Komisyon formülü: online satırda hakediş = tutar × oran; kapıda satırda indirim/kupon düşülmüş tutar × oran."""
    if s.empty:
        return BOS
    taban = s["tutar"] + np.where(s["tur"] == "ty_kapida", s["s_ind"] + s["s_kup"], 0.0)
    beklenen = (taban * s["oran"] / 100).round(2)
    s = s.assign(beklenen=beklenen, fark=(s["ty_hak"] - beklenen).round(2))
    baskin = s.groupby("magaza")["oran"].agg(_mod)
    s["baskin_oran"] = s["magaza"].map(baskin)
    return s[(s["fark"].abs() > 0.02) | (s["oran"] != s["baskin_oran"])]


def _ty_siparisler(s: pd.DataFrame):
    if s.empty:
        return BOS, BOS
    s = _en_yeni(s, ["tur", "kayit"])
    indirim_tipi = s["tip"].isin(["İndirim", "Kupon"])
    iade_tipi = s["tip"].isin(["İade", "Kısmi İade"])
    s = s.assign(
        brut=np.where(s["tip"] == "Satış", s["tutar"], 0.0),
        iade=np.where(iade_tipi, -s["tutar"], 0.0),
        kampanya_tl=np.where(indirim_tipi, -s["tutar"], 0.0) - s["s_ind"] - s["s_kup"],
        bilinmeyen=np.where(~(indirim_tipi | iade_tipi | (s["tip"] == "Satış")), s["tutar"], 0.0),
    )
    o = s.groupby(["magaza", "siparis"]).agg(
        zaman=("zaman", "min"), uygulama=("uygulama", "first"), odeme=("odeme", "first"),
        brut=("brut", "sum"), iade=("iade", "sum"), kampanya=("kampanya_tl", "sum"), bilinmeyen=("bilinmeyen", "sum"),
        platform_ind=("p_ind", "sum"), komisyon=("ty_hak", "sum"), kalan=("satici_hak", "sum")).reset_index()
    o["platform"], o["reklam"], o["joker"] = TY, 0.0, False
    o["platform_ind"] = -o["platform_ind"]
    o["uygulama"] = o["uygulama"].str.replace("Uber Eats TrendyolGo", "TrendyolGo").str.replace("GetirYemek by Uber Eats", "GetirYemek")

    # kampanya kullanımları (sipariş × kampanya)
    k1 = s[indirim_tipi].assign(kampanya=lambda x: x["urun"].map(ty_kampanya_adi), maliyet=lambda x: -x["tutar"])
    k2 = s[s["s_ind"] != 0].assign(kampanya="Kapıda ödeme indirimi (adı yok)", maliyet=lambda x: -x["s_ind"])
    k3 = s[s["s_kup"] != 0].assign(kampanya="Kapıda ödeme kuponu (adı yok)", maliyet=lambda x: -x["s_kup"])
    k = pd.concat([k1, k2, k3])
    if len(k):
        k = k.groupby(["magaza", "siparis", "kampanya"], as_index=False)["maliyet"].sum()
        k["platform"], k["platform_maliyet"] = TY, 0.0
    return o, k


# ---- Yemeksepeti

def _ys_siparisler(g: Girdi):
    df = g.tablolar.get("ys_siparis")
    if df is None:
        return BOS, BOS, BOS
    df = _en_yeni(df, ["Sipariş No"])
    fat = df["Faturalandırılabilir"].astype(str).str.strip().str.lower()
    e = df[fat.isin(["evet", "yes", "y", "true", "1"])]

    def n(c):
        return sayilar(e[c]) if c in e.columns else pd.Series(0.0, index=e.index)

    ara, ind, kup = n("Ara Toplam"), n("İndirim (İşletme tarafından karşılandı)"), n("Kupon (İşletme tarafından karşılandı)")
    kom, vergi, rek = n("Komisyon"), n("Vergi ücreti"), n("Reklam ücreti")
    joker = e.get("Pazarlama ücretlerinin nedenleri", pd.Series("", index=e.index)).astype(str).str.contains("Joker", case=False)
    o = pd.DataFrame({
        "magaza": e["Restoran Adı"].map(_ad), "magaza_no": e["Şube No"].astype(str).str.strip(),
        "siparis": e["Sipariş No"].astype(str).str.strip(), "zaman": tarih_iso(e["Siparişin Alındığı Zaman"]),
        "uygulama": "Yemeksepeti",
        "odeme": np.where(e["Ödeme Türü"].astype(str).str.strip() == "Online", "Online", "Kapıda"),
        "brut": ara, "iade": n("Restoran para iadeleri"), "kampanya": ind + kup,
        "platform_ind": n("Yemeksepeti tarafından finanse edilen indirim") + n("Yemeksepeti tarafından finanse edilen kupon"),
        "komisyon": kom * (1 + KDV), "reklam": rek * (1 + KDV), "kalan": n("Tahmini Kazanç"),
        "nakit": n("İşletme tarafından tahsil edilmiş nakit tutar"), "ys_kupon": n("Yemeksepeti tarafından finanse edilen kupon"),
        "ham_kom": kom, "vergi": vergi, "joker": joker, "bilinmeyen": 0.0,
    })
    o["platform"] = YS
    # Beklenen vergi: komisyon ve reklam ücretinin KDV'si; online siparişte ayrıca KDV hariç tabanın %1'i (stopaj)
    taban = o["brut"] - o["kampanya"]
    o["stopaj_bekl"] = np.where(o["odeme"] == "Online", 0.01 * taban / 1.1, 0.0)
    o["vergi_bekl"] = KDV * (kom + rek) + o["stopaj_bekl"]
    o["kom_oran"] = np.where(o["joker"], kom / ara.replace(0, np.nan), kom / taban.replace(0, np.nan)) * 100

    # kampanya kullanımları
    rows = []
    for i, r in o.iterrows():
        if ind[i] > 0:
            oran = ind[i] / ara[i] * 100 if ara[i] else 0
            rows.append((r.magaza, r.siparis, f"%{oran:.0f} indirim", ind[i], 0.0))
        if kup[i] > 0:
            ad = f"Joker kuponu ({kup[i]:.0f} TL)" if r.joker else f"{kup[i]:.0f} TL kupon"
            rows.append((r.magaza, r.siparis, ad, kup[i], 0.0))
        if r.platform_ind > 0:
            rows.append((r.magaza, r.siparis, "Yemeksepeti'nin karşıladığı kupon/indirim", 0.0, r.platform_ind))
    k = pd.DataFrame(rows, columns=["magaza", "siparis", "kampanya", "maliyet", "platform_maliyet"])
    k["platform"] = YS
    return o, k, df


def _ys_fatura(g: Girdi, ys: pd.DataFrame) -> pd.DataFrame:
    df = g.tablolar.get("ys_fatura")
    if df is None:
        return BOS
    df = _en_yeni(df, ["Fatura No"])
    n = lambda c: sayilar(df[c]) if c in df.columns else pd.Series(0.0, index=df.index)  # noqa: E731
    nedenler = df.get("Ek Ücret Nedenleri", pd.Series("", index=df.index)).astype(str)
    f = pd.DataFrame({
        "fatura_no": df["Fatura No"].astype(str).str.strip(),
        "bas": tarih_iso(df["Başlangıç Tarihi"]).dt.date, "bit": tarih_iso(df["Bitiş Tarihi"]).dt.date,
        "toplam_kazanc": n("Toplam Kazanç"), "siparis": n("Sipariş Sayısı").astype(int), "nakit": -n("Tahsil Edilen Nakit Tutarı"),
        "toplam_odeme": n("Toplam Ödeme"), "brut": n("Brüt Satışlar"), "komisyon": -n("Komisyon Bedeli"),
        "ek_ucret": -n("Toplam Ek Ücretler"), "ek_neden": nedenler,
        "ind": -n("İşletme Tarafından Karşılanan İndirimler"), "kup": -n("İşletme Tarafından Karşılanan Kuponlar"),
        "pazarlama": -n("Pazarlama Ücretleri"), "_dosya": df["_dosya"],
    })
    reklam_mi = f["ek_neden"].str.contains("CPC|Reklam", case=False, regex=True)
    f["cpc"] = np.where(reklam_mi, f["ek_ucret"], 0.0)
    f["diger_ek"] = np.where(reklam_mi, 0.0, f["ek_ucret"])
    # mağaza: dönemin sipariş sayısı ve brüt satışı hangi mağazanınkiyle tutuyorsa
    f["magaza"] = ""
    if not ys.empty:
        for i, r in f.iterrows():
            aday = []
            w = ys[(ys["zaman"].dt.date >= r.bas) & (ys["zaman"].dt.date <= r.bit)]
            for m, x in w.groupby("magaza"):
                brut = (x["brut"] - x["ys_kupon"]).sum()
                if len(x) == r.siparis and abs(brut - r.brut) < 1:
                    aday.append(m)
            if len(aday) == 1:
                f.at[i, "magaza"] = aday[0]
    return f


# ---- Trendyol fatura listesi ve reklam

def _ty_fatura(g: Girdi, dosyalar: pd.DataFrame) -> pd.DataFrame:
    df = g.tablolar.get("ty_fatura")
    if df is None:
        return BOS
    f = pd.DataFrame({
        "fatura_no": df["Fatura No"].astype(str).str.strip(), "tutar": -sayilar(df["Tutar"]),
        "tip": df["Fatura Tipi"].astype(str).str.strip(), "zaman": tarih_tr(df["Fatura Tarihi"]),
        "statu": df.get("Statü", pd.Series("", index=df.index)).astype(str), "_dosya": df["_dosya"], "_zaman": df["_zaman"],
    })
    f["tutar_r"] = f["tutar"].round(2)
    # Liste dosyası tek satıcı hesabına aittir: komisyon/kapıda faturalarının tutarları hangi mağazanın detaylarıyla tutuyorsa
    f["magaza"] = ""
    if not dosyalar.empty:
        harita = dosyalar.groupby("tutar")["magaza"].agg(lambda x: x.iloc[0] if x.nunique() == 1 else "")
        for dosya, x in f.groupby("_dosya"):
            m = x["tutar_r"].map(harita).dropna()
            m = m[m != ""]
            if len(m):
                f.loc[f["_dosya"] == dosya, "magaza"] = m.mode().iloc[0]
    f["liste_ilk"] = f.groupby("magaza")["zaman"].transform("min")
    return _en_yeni(f, ["fatura_no"])


def _ty_reklam(g: Girdi, magaza_adlari: dict) -> pd.DataFrame:
    df = g.tablolar.get("ty_reklam")
    if df is None:
        return BOS
    r = pd.DataFrame({
        "magaza_no": _no(df["Şube No"]),
        "magaza": df.get("Şube Adı", pd.Series("", index=df.index)).map(_ad),
        "gun": pd.to_datetime(df["Gün"], errors="coerce").dt.date,
        "kampanya": df["_kampanya"], "bolge": df.get("Bölge Adı", pd.Series("", index=df.index)).fillna("").astype(str),
        "harcama": sayilar(df["Reklam Harcaması"]), "gosterim": sayilar(df["Gösterim Sayısı"]),
        "tiklama": sayilar(df["Tıklanma Sayısı"]), "satis": sayilar(df["Satış Adedi"]),
        "yeni": sayilar(df["Yeni Müşteri Sayısı"]), "ciro": sayilar(df["Ciro"]), "_zaman": df["_zaman"],
    })
    r["magaza"] = np.where(r["magaza"] == "", r["magaza_no"].map(magaza_adlari).fillna(r["magaza_no"]), r["magaza"])
    return _en_yeni(r.dropna(subset=["gun"]), ["magaza_no", "kampanya", "gun", "bolge"])


def _reklam_kampanyalari(r: pd.DataFrame, f: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reklam Bedeli faturalarını kampanyalara bağlar; kampanya başına harcama ile faturayı karşılaştırır."""
    if r.empty:
        return BOS, BOS
    k = r.groupby(["magaza", "kampanya"]).agg(ilk=("gun", "min"), son=("gun", "max"), harcama=("harcama", "sum"),
                                              gun=("gun", lambda x: x[r.loc[x.index, "harcama"] > 0].nunique())).reset_index()
    k["baslangic"] = [reklam_kodu_zamani(c, i) for c, i in zip(k["kampanya"], k["ilk"])]
    rf = f[f["tip"] == "Reklam Bedeli"].copy() if not f.empty else pd.DataFrame(columns=["magaza", "zaman", "tutar"])
    rf["kampanya"] = ""
    gunluk = r[r["harcama"] > 0].groupby(["magaza", "gun"])["kampanya"].apply(list)
    for i, x in rf.iterrows():
        km = k[k["magaza"] == x.magaza]
        if km.empty or pd.isna(x.zaman):
            continue
        t = x.zaman.to_pydatetime()
        tam = km[km["baslangic"].map(lambda b: b is not None and abs((b - t).total_seconds()) <= 180)]
        if len(tam):
            rf.at[i, "kampanya"] = tam["kampanya"].iloc[0]
            continue
        if t.hour == 0 and t.minute <= 40:  # günlük bütçe: o günün başında o gün için kesilir
            aday = gunluk.get((x.magaza, t.date()), [])
            if aday:
                rf.at[i, "kampanya"] = aday[0]
                continue
        acik = km[km["baslangic"].map(lambda b: b is not None and b <= t) & (km["son"] >= t.date())]
        if len(acik):
            rf.at[i, "kampanya"] = acik["kampanya"].iloc[0]
            continue
        sonraki = km[km["baslangic"].map(lambda b: b is not None and t < b <= t + timedelta(days=7))]
        if len(sonraki):
            rf.at[i, "kampanya"] = sonraki.sort_values("baslangic")["kampanya"].iloc[0]
    fat = rf[rf["kampanya"] != ""].groupby(["magaza", "kampanya"]).agg(fatura=("tutar", "sum"), fatura_adet=("tutar", "size"))
    k = k.merge(fat, on=["magaza", "kampanya"], how="left").fillna({"fatura": 0.0, "fatura_adet": 0})
    tum_ilk = f.groupby("magaza")["zaman"].min() if not f.empty else pd.Series(dtype="datetime64[ns]")
    k["fark"] = (k["fatura"] - k["harcama"]).round(2)

    def durum(x):
        ilk = tum_ilk.get(x.magaza)
        if ilk is None or pd.isna(ilk):
            return "Fatura listesi yok"
        if x.fatura == 0:
            if x.baslangic is not None and x.baslangic < ilk.to_pydatetime() - timedelta(minutes=5):
                return "Fatura listesi bu tarihi kapsamıyor"
            # Bazı kampanyalarda reklam bedelinin bir bölümünü ya da tamamını Trendyol karşılıyor (kullanıcı doğruladı)
            return "Tamamını Trendyol karşıladı" if x.harcama > 0 else "Harcama yok"
        if abs(x.fark) < 1:
            return "Tutuyor"
        return "Fatura harcamadan fazla" if x.fark > 0 else "Bir bölümünü Trendyol karşıladı"
    k["durum"] = k.apply(durum, axis=1)
    kapsar = ~k["durum"].isin(["Fatura listesi yok", "Fatura listesi bu tarihi kapsamıyor"])
    k["trendyol_payi"] = np.where(kapsar, (k["harcama"] - k["fatura"]).clip(lower=0), 0.0).round(2)
    # Restoranın payı: kesilen fatura; fatura listesi kampanyayı kapsamıyorsa harcamanın tamamı varsayılır
    k["restoran_payi"] = np.where(kapsar, k["fatura"], k["harcama"])
    return k.sort_values(["magaza", "ilk"]), rf


# ---- değerlendirmeler ve performans

def _ty_deg(g: Girdi, magaza_adlari: dict) -> pd.DataFrame:
    df = g.tablolar.get("ty_degerlendirme")
    if df is None:
        return BOS
    d = pd.DataFrame({
        "magaza": df["_magaza_no"].map(magaza_adlari).fillna(df["_magaza_no"]),
        "zaman": tarih_tr(df["Sipariş Tarihi"]), "deg_zaman": tarih_tr(df["Değerlendirme Tarihi"]),
        "lezzet": sayilar(df["Lezzet Puanı"]), "servis": sayilar(df["Servis Puanı"]),
        "teslimat": sayilar(df["Teslimat Puanı"]), "puan": sayilar(df["Ortalama Puan"]),
        "metin": df["Müşteri Mesajı"].fillna("").astype(str).str.strip(),
        "cevap": df["Restoran Cevabı"].fillna("").astype(str).str.strip(),
        "urunler": df.get("Beğenilen Ürünler", pd.Series("", index=df.index)).fillna("").astype(str),
        "_zaman": df["_zaman"],
    })
    d["metin"] = d["metin"].replace("nan", "")
    d["cevap"] = d["cevap"].replace("nan", "")
    d["platform"] = TY
    return _en_yeni(d, ["magaza", "zaman", "deg_zaman", "puan", "metin"])


def _ys_deg(g: Girdi, ys: pd.DataFrame, ys_adlar: dict) -> pd.DataFrame:
    df = g.tablolar.get("ys_degerlendirme")
    if df is None:
        return BOS
    df = _en_yeni(df, ["Sipariş kimliği"])
    d = pd.DataFrame({
        "magaza": df["Restoran adı"].map(_ad) if "Restoran adı" in df else df["Satıcı Kimliği"].map(ys_adlar),
        "siparis": df["Sipariş kimliği"].astype(str).str.strip(), "deg_zaman": tarih_iso(df["Tarih"]),
        "puan": sayilar(df["Puan"]), "metin": df["İnceleme metni"].fillna("").astype(str).str.strip(),
    })
    zaman = ys.set_index("siparis")["zaman"] if not ys.empty else pd.Series(dtype="datetime64[ns]")
    d["zaman"] = d["siparis"].map(zaman).fillna(d["deg_zaman"])
    d["cevap"], d["platform"], d["lezzet"], d["servis"], d["teslimat"], d["urunler"] = "", YS, np.nan, np.nan, np.nan, ""
    return d


PERF_SAYISAL = {
    "Başarılı siparişler": "basarili", "Brüt satışlar": "brut", "İptal edilen siparişler": "iptal",
    "İşletme Kaynaklı İptal Edilen Siparişler": "isletme_iptal", "Müsait olmama süresi (Dakika)": "kapali_dk",
    "Planlanan açılma zamanı (dakika)": "planli_dk", "Ortalama hazırlama süresi (dakika)": "hazirlama",
    "Alınan Toplam Müşteri Şikayeti": "sikayet", "Yeni müşteri siparişleri": "yeni", "Dönen müşteri siparişleri": "donen",
    "Görüntülenme Sayısı": "goruntulenme", "Menü Görüntüleme Sayısı": "menu", "Sepete eklenen ürünler": "sepet",
    "Sipariş Veren Müşteri Sayısı": "musteri",
}


def _ys_perf(g: Girdi) -> pd.DataFrame:
    df = g.tablolar.get("ys_performans")
    if df is None:
        return BOS
    df = _en_yeni(df, ["Restoran No", "Tarih"])
    p = pd.DataFrame({"magaza": df["Şube Adı"].map(_ad), "gun": tarih_iso(df["Tarih"]).dt.date})
    for c, k in PERF_SAYISAL.items():
        p[k] = sayilar(df[c]) if c in df.columns else 0.0
    return p.dropna(subset=["gun"])


# ---------------------------------------------------------------- ana kurulum

def kur(g: Girdi, baslangic: date) -> Analiz:
    uyarilar: list[Uyari] = []
    ty_s = _ty_satirlar(g)
    ty_dosya = _ty_dosya_ozeti(ty_s)
    ty_sapma = _ty_satir_sapmalari(ty_s)
    ty_o, ty_k = _ty_siparisler(ty_s)
    ys_o, ys_k, _ = _ys_siparisler(g)

    magaza_adlari = {}
    if not ty_s.empty:
        magaza_adlari.update(ty_s.drop_duplicates("magaza_no").set_index("magaza_no")["magaza"].to_dict())
    if "ty_reklam" in g.tablolar:
        r0 = g.tablolar["ty_reklam"]
        if "Şube Adı" in r0:
            for no, ad in zip(_no(r0["Şube No"]), r0["Şube Adı"].map(_ad)):
                magaza_adlari.setdefault(no, ad)
    ys_adlar = ys_o.drop_duplicates("magaza_no").set_index("magaza_no")["magaza"].to_dict() if not ys_o.empty else {}

    ty_f = _ty_fatura(g, ty_dosya)
    ty_r = _ty_reklam(g, magaza_adlari)
    ty_rk, ty_rf = _reklam_kampanyalari(ty_r, ty_f)
    if not ty_f.empty and len(ty_rf):
        ty_f = ty_f.merge(ty_rf[["fatura_no", "kampanya"]], on="fatura_no", how="left")
    ys_f = _ys_fatura(g, ys_o)
    ys_p = _ys_perf(g)
    ty_d = _ty_deg(g, magaza_adlari)
    ys_d = _ys_deg(g, ys_o, ys_adlar)

    # ---- veri kapsamı: analiz, iki platformun da tam verisi olan son fatura dönemiyle biter
    uclar = {}
    online = ty_dosya[ty_dosya["tur"] == "ty_online"] if not ty_dosya.empty else BOS
    if not online.empty:
        uclar[TY] = max(donem_bit(d) for d in online["donem"])
    if not ys_p.empty:
        uclar[YS] = max(ys_p["gun"])
    elif not ys_o.empty:
        uclar[YS] = ys_o["zaman"].max().date() - timedelta(days=1)
    if not uclar:
        raise SystemExit(3)
    uc = min(uclar.values())
    p = donem_bas(uc)
    son = donem_bit(p) if donem_bit(p) <= uc else p - timedelta(days=1)
    bas = baslangic
    dlist = donemler(bas, son)

    sip = pd.concat([x for x in (ty_o, ys_o) if not x.empty], ignore_index=True)
    sip["gun"] = sip["zaman"].dt.date
    sip["donem"] = sip["gun"].map(donem_bas)
    for c in ("reklam", "iade", "kampanya", "platform_ind", "bilinmeyen"):
        sip[c] = sip[c].fillna(0.0)
    sip["diger"] = (sip["brut"] - sip["iade"] - sip["kampanya"] - sip["komisyon"] - sip["reklam"] - sip["kalan"]).round(2)
    kamp = pd.concat([x for x in (ty_k, ys_k) if not x.empty], ignore_index=True)
    if len(kamp):
        kamp = kamp.merge(sip[["platform", "siparis", "gun", "brut"]], on=["platform", "siparis"], how="left")

    magazalar = sorted(set(sip["magaza"]) | (set(ty_r["magaza"]) if not ty_r.empty else set()))

    # ---- Yemeksepeti sipariş düzeyi sapmalar
    ys_sapma = BOS
    if not ys_o.empty:
        y = sip[sip["platform"] == YS].copy()
        baskin = y[~y["joker"]].groupby("magaza")["kom_oran"].agg(lambda x: _mod(x.round(1)))
        y["baskin"] = y["magaza"].map(baskin)
        y["kazanc_bekl"] = (y["brut"] - y["iade"] - y["kampanya"] - y["ham_kom"] * (1 + KDV) - y["reklam"]
                            - y["stopaj_bekl"]).round(2)
        neden = []
        for _, r in y.iterrows():
            n = []
            if abs(r.kalan - r.kazanc_bekl) > 1:
                n.append(f"Kazanç beklenenden {r.kazanc_bekl - r.kalan:,.2f} TL düşük" if r.kalan < r.kazanc_bekl
                         else f"Kazanç beklenenden {r.kalan - r.kazanc_bekl:,.2f} TL yüksek")
            elif abs(r.vergi - r.vergi_bekl) > 0.05:
                n.append("Vergi kesintisi formülle tutmuyor")
            if not r.joker and pd.notna(r.kom_oran) and abs(r.kom_oran - r.baskin) > 0.15:
                n.append(f"Komisyon oranı %{r.kom_oran:.1f} (olağan %{r.baskin:.1f})")
            neden.append("; ".join(n))
        y["neden"] = neden
        ys_sapma = y[y["neden"] != ""]

    # ---- ürünler: Trendyol'da her satış satırı bir adet; Yemeksepeti'nde ürün satışları raporu
    urunler = []
    if not ty_s.empty:
        u = _en_yeni(ty_s, ["tur", "kayit"])
        u = u[u["tip"] == "Satış"]
        urunler.append(pd.DataFrame({"platform": TY, "magaza": u["magaza"], "gun": u["zaman"].dt.date,
                                     "urun": u["urun"].map(_tirnak), "adet": 1.0, "ciro": u["tutar"]}))
    yu = g.tablolar.get("ys_urun")
    if yu is not None:
        # Aynı gün aynı ürün farklı fiyatlarla birden çok satır olabilir; satır anahtarı yok. Bu yüzden her mağaza-gün
        # için yalnız o günü içeren en yeni dosyanın satırları alınır (çakışan dosyalar iki kez sayılmaz).
        en_yeni = yu.groupby(["Satıcı Kimliği", "Tarih"])["_zaman"].transform("max")
        yu = yu[yu["_zaman"] == en_yeni]
        yu = yu[~yu.duplicated([c for c in yu.columns if c not in ("_dosya", "_sha")])]  # aynı zamanlı birebir kopyalar
        urunler.append(pd.DataFrame({"platform": YS, "magaza": yu["Satıcı Kimliği"].astype(str).str.strip().map(ys_adlar),
                                     "gun": tarih_iso(yu["Tarih"]).dt.date, "urun": yu["Menü öğesi adı"].map(_tirnak),
                                     "adet": sayilar(yu["Adet"]), "ciro": sayilar(yu["Gelir"])}).dropna(subset=["magaza", "gun"]))
    urun = pd.concat(urunler, ignore_index=True) if urunler else BOS

    numaralar: dict = {}
    for no, ad in magaza_adlari.items():
        numaralar.setdefault(ad, {})[TY] = no
    for no, ad in ys_adlar.items():
        numaralar.setdefault(ad, {})[YS] = no

    a = Analiz(bas=bas, son=son, donemler=dlist, magazalar=magazalar, siparis=sip, kampanya=kamp,
               ty_dosya=ty_dosya, ty_satir_sapma=ty_sapma, ty_fatura=ty_f, ty_reklam=ty_r, ty_reklam_kampanya=ty_rk,
               ty_deg=ty_d, ys_fatura=ys_f, ys_sapma=ys_sapma, ys_perf=ys_p, ys_deg=ys_d,
               kapsam={"uclar": uclar, "ty_satir": len(ty_s)}, uyarilar=uyarilar, urun=urun, magaza_no=numaralar)
    _uyarilari_topla(a)
    return a


# ---------------------------------------------------------------- tablolar (mağaza başına)

def _pencere(df: pd.DataFrame, a: Analiz, sutun="gun") -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df[sutun] >= a.bas) & (df[sutun] <= a.son)]


def platformlar(a: Analiz, m: str) -> list[str]:
    s = a.siparis
    return [p for p in (TY, YS) if ((s["magaza"] == m) & (s["platform"] == p)).any()]


def ty_reklam_faturasi(a: Analiz, m: str) -> pd.DataFrame:
    f = a.ty_fatura
    if f.empty:
        return BOS
    x = f[(f["magaza"] == m) & (f["tip"] == "Reklam Bedeli")].copy()
    x["gun"] = x["zaman"].dt.date
    return x


def ty_reklam_gunluk(a: Analiz, m: str) -> pd.DataFrame:
    """Gün başına Trendyol reklam harcaması ve restoranın payı (maliyet). Restoranın payı, kampanyaya kesilen Reklam Bedeli
    faturalarının kampanyanın harcama günlerine harcamayla orantılı dağıtılmasıyla bulunur: bazı kampanyalarda bedelin bir
    bölümünü ya da tamamını Trendyol karşılıyor. Günlük bütçeli kampanyada harcanmayan bütçe de restoranın payına girer."""
    if a.ty_reklam.empty:
        return pd.DataFrame(columns=["harcama", "maliyet"])
    r = a.ty_reklam[a.ty_reklam["magaza"] == m]
    if r.empty:
        return pd.DataFrame(columns=["harcama", "maliyet"])
    rk = a.ty_reklam_kampanya
    rk = rk[rk["magaza"] == m].set_index("kampanya") if not rk.empty else pd.DataFrame()
    katsayi = {k: (x.restoran_payi / x.harcama if x.harcama > 0 else 0.0) for k, x in rk.iterrows()}
    r = r.assign(maliyet=r["harcama"] * r["kampanya"].map(katsayi).fillna(1.0))
    return r.groupby("gun")[["harcama", "maliyet"]].sum()


def trend(a: Analiz, m: str) -> pd.DataFrame:
    """Dönem × platform: sipariş, brüt, iade, kampanya, komisyon, reklam, diğer, restorana kalan."""
    s = _pencere(a.siparis[a.siparis["magaza"] == m], a)
    rf = ty_reklam_faturasi(a, m)
    tr = a.ty_reklam[a.ty_reklam["magaza"] == m] if not a.ty_reklam.empty else BOS
    rg = ty_reklam_gunluk(a, m)
    yf = a.ys_fatura[a.ys_fatura["magaza"] == m] if not a.ys_fatura.empty else BOS
    satirlar = []
    for b, e in a.donemler:
        gun = (e - b).days + 1
        for p in platformlar(a, m):
            x = s[(s["platform"] == p) & (s["gun"] >= b) & (s["gun"] <= e)]
            satis = x[x["brut"] > 0]
            r = {"bas": b, "bit": e, "gun": gun, "platform": p, "siparis": len(satis), "brut": x["brut"].sum(),
                 "iade": x["iade"].sum(), "kampanya": x["kampanya"].sum(), "komisyon": x["komisyon"].sum(),
                 "reklam": x["reklam"].sum(), "diger": x["diger"].sum(), "kalan": x["kalan"].sum(), "reklam_eksik": False}
            if p == TY:
                # Restoranın reklam payı: kampanyaya kesilen Reklam Bedeli, kampanyanın harcama günlerine harcamayla orantılı
                # dağıtılır (toplu peşin faturalar dönemleri çarpıtmaz; Trendyol'un karşıladığı kısım restorana yazılmaz).
                # Reklam raporu yoksa fatura tarihine göre faturalanan tutar.
                if not tr.empty:
                    ek = rg[(rg.index >= b) & (rg.index <= e)]["maliyet"].sum()
                else:
                    ek = rf[(rf["gun"] >= b) & (rf["gun"] <= e)]["tutar"].sum() if not rf.empty else 0.0
                r["reklam"] += ek
                r["kalan"] -= ek
            else:
                fx = yf[(yf["bas"] == b) | ((yf["bas"] <= b) & (yf["bit"] >= e))] if not yf.empty else BOS
                if len(fx):
                    cpc = (fx["cpc"] * (1 + KDV)).sum() + (fx["diger_ek"] * (1 + KDV)).sum()
                    r["reklam"] += cpc
                    r["kalan"] -= cpc
                elif len(satis):
                    r["reklam_eksik"] = True
            satirlar.append(r)
    t = pd.DataFrame(satirlar)
    if t.empty:
        return t
    t["net"] = t["brut"] - t["iade"] - t["kampanya"]
    return t


def toplam_trend(t: pd.DataFrame) -> pd.DataFrame:
    if t.empty:
        return t
    sayisal = ["siparis", "brut", "iade", "kampanya", "komisyon", "reklam", "diger", "kalan", "net"]
    g = t.groupby(["bas", "bit", "gun"], as_index=False).agg({**{c: "sum" for c in sayisal}, "reklam_eksik": "any"})
    g["platform"] = "Toplam"
    return g


def aylik(t: pd.DataFrame) -> pd.DataFrame:
    if t.empty:
        return t
    x = t.copy()
    x["ay"] = x["bas"].map(lambda d: (d.year, d.month))
    sayisal = ["siparis", "brut", "iade", "kampanya", "komisyon", "reklam", "diger", "kalan", "net", "gun"]
    g = x.groupby(["ay", "platform"], as_index=False).agg({**{c: "sum" for c in sayisal}, "reklam_eksik": "any",
                                                           "bas": "min", "bit": "max"})
    return g


# ---- fatura kontrolü

def ty_komisyon_kontrol(a: Analiz, m: str, tur: str) -> pd.DataFrame:
    d = a.ty_dosya
    f = a.ty_fatura
    if d.empty:
        return BOS
    d = d[(d["magaza"] == m) & (d["tur"] == tur)].copy()
    tip = "Komisyon Faturası" if tur == "ty_online" else "Kapıda Ödeme İşlemleri Komisyon Kesinti Faturası"
    ff = f[(f["magaza"] == m) & (f["tip"] == tip)].copy() if not f.empty else pd.DataFrame(columns=["fatura_no", "tutar_r", "zaman", "tutar"])
    kullanilan = set()
    rows = []
    for _, r in d.sort_values("ilk").iterrows():
        aday = ff[(ff["tutar_r"] == r.tutar) & ~ff["fatura_no"].isin(kullanilan)]
        if len(aday):
            # aynı tutarda birden çok fatura olabilir: detaydaki son siparişten sonra kesilen en yakın fatura
            uzaklik = (aday["zaman"] - r.son).dt.total_seconds()
            uzaklik = uzaklik.where(uzaklik >= -86400, uzaklik.abs() + 1e9)
            x = aday.loc[uzaklik.idxmin()]
            kullanilan.add(x.fatura_no)
            rows.append({"donem": r.donem, "ilk": r.ilk, "son": r.son, "fatura_no": x.fatura_no, "fatura_tarihi": x.zaman,
                         "fatura": x.tutar, "detay": r.tutar, "fark": round(x.tutar - r.tutar, 2), "durum": "Tuttu"})
        else:
            durum = "Fatura listesi yok" if ff.empty and f.empty else "Listede bu tutarda fatura yok"
            rows.append({"donem": r.donem, "ilk": r.ilk, "son": r.son, "fatura_no": "", "fatura_tarihi": pd.NaT,
                         "fatura": np.nan, "detay": r.tutar, "fark": np.nan, "durum": durum})
    for _, x in ff[~ff["fatura_no"].isin(kullanilan)].iterrows():
        rows.append({"donem": donem_bas(x.zaman.date()) if pd.notna(x.zaman) else None, "ilk": pd.NaT, "son": pd.NaT,
                     "fatura_no": x.fatura_no, "fatura_tarihi": x.zaman, "fatura": x.tutar, "detay": np.nan, "fark": np.nan,
                     "durum": "Detay dosyası yok"})
    k = pd.DataFrame(rows)
    if k.empty:
        return k
    k = k.sort_values("fatura_tarihi", na_position="last")
    # analiz penceresi: dönemi pencereyle kesişenler
    return k[k["donem"].map(lambda d: d is not None and d <= a.son and donem_bit(d) >= a.bas)]


def ty_reklam_donem(a: Analiz, m: str) -> pd.DataFrame:
    r = _pencere(a.ty_reklam[a.ty_reklam["magaza"] == m], a) if not a.ty_reklam.empty else BOS
    rf = ty_reklam_faturasi(a, m)
    rf = _pencere(rf, a) if not rf.empty else rf
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == TY) & (a.siparis["brut"] > 0)], a)
    rg = ty_reklam_gunluk(a, m)
    rows = []
    for b, e in a.donemler:
        x = r[(r["gun"] >= b) & (r["gun"] <= e)] if not r.empty else BOS
        fx = rf[(rf["gun"] >= b) & (rf["gun"] <= e)] if not rf.empty else BOS
        sx = s[(s["gun"] >= b) & (s["gun"] <= e)]
        rows.append({"bas": b, "bit": e, "gun": (e - b).days + 1,
                     "reklam_gun": int((x.groupby("gun")["harcama"].sum() > 0).sum()) if len(x) else 0,
                     "harcama": x["harcama"].sum() if len(x) else 0.0, "fatura": fx["tutar"].sum() if len(fx) else 0.0,
                     "maliyet": rg[(rg.index >= b) & (rg.index <= e)]["maliyet"].sum() if len(rg) else 0.0,
                     "gosterim": x["gosterim"].sum() if len(x) else 0, "tiklama": x["tiklama"].sum() if len(x) else 0,
                     "satis": x["satis"].sum() if len(x) else 0, "ciro": x["ciro"].sum() if len(x) else 0.0,
                     "yeni": x["yeni"].sum() if len(x) else 0, "ty_siparis": len(sx)})
    return pd.DataFrame(rows)


def ty_reklamli_gunler(a: Analiz, m: str) -> pd.DataFrame:
    """Trendyol'da reklamlı ve reklamsız günlerin günlük ortalamaları (yalnız Trendyol verisinin kapsadığı günler)."""
    if a.ty_reklam.empty:
        return BOS
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == TY)], a)
    if s.empty:
        return BOS
    gunler = pd.date_range(a.bas, a.son).date
    gs = s[s["brut"] > 0].groupby("gun").agg(siparis=("siparis", "size"), brut=("brut", "sum"))
    gk = s.groupby("gun")["kalan"].sum()
    h = a.ty_reklam[a.ty_reklam["magaza"] == m].groupby("gun")["harcama"].sum()
    d = pd.DataFrame(index=gunler)
    d["siparis"] = gs["siparis"].reindex(gunler).fillna(0).values
    d["brut"] = gs["brut"].reindex(gunler).fillna(0).values
    d["kalan"] = gk.reindex(gunler).fillna(0).values
    d["harcama"] = h.reindex(gunler).fillna(0).values
    d["reklamli"] = d["harcama"] > 0
    g = d.groupby("reklamli").agg(gun=("siparis", "size"), siparis=("siparis", "mean"), brut=("brut", "mean"),
                                  harcama=("harcama", "mean"))
    return g


def ys_reklam_donem(a: Analiz, m: str) -> pd.DataFrame:
    p = _pencere(a.ys_perf[a.ys_perf["magaza"] == m], a) if not a.ys_perf.empty else BOS
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == YS)], a)
    yf = a.ys_fatura[a.ys_fatura["magaza"] == m] if not a.ys_fatura.empty else BOS
    rows = []
    for b, e in a.donemler:
        x = p[(p["gun"] >= b) & (p["gun"] <= e)] if len(p) else BOS
        sx = s[(s["gun"] >= b) & (s["gun"] <= e)]
        fx = yf[yf["bas"] == b] if len(yf) else BOS
        rows.append({"bas": b, "bit": e, "gun": (e - b).days + 1,
                     "cpc": (fx["cpc"].sum() * (1 + KDV)) if len(fx) else np.nan,
                     "joker": sx["reklam"].sum(), "joker_siparis": int(sx["joker"].sum()),
                     "goruntulenme": x["goruntulenme"].sum() if len(x) else np.nan, "menu": x["menu"].sum() if len(x) else np.nan,
                     "sepet": x["sepet"].sum() if len(x) else np.nan, "musteri": x["musteri"].sum() if len(x) else np.nan,
                     "siparis": int((sx["brut"] > 0).sum())})
    return pd.DataFrame(rows)


def ys_fatura_kontrol(a: Analiz, m: str) -> pd.DataFrame:
    s = a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == YS)]
    yf = a.ys_fatura[a.ys_fatura["magaza"] == m] if not a.ys_fatura.empty else BOS
    rows = []
    for b, e in a.donemler:
        x = s[(s["gun"] >= b) & (s["gun"] <= e)]
        fx = yf[yf["bas"] == b] if len(yf) else BOS
        hesap = {"siparis": len(x), "brut": (x["brut"] - x["ys_kupon"]).sum(), "komisyon": x["ham_kom"].sum(),
                 "ind_kup": x["kampanya"].sum(), "nakit": x["nakit"].sum(), "kazanc": x["kalan"].sum()}
        if len(fx):
            f = fx.iloc[0]
            beklenen = round(hesap["kazanc"] - round(f.cpc * (1 + KDV), 2) - round(f.diger_ek * (1 + KDV), 2), 2)
            farklar = {"sipariş": f.siparis - hesap["siparis"], "brüt": f.brut - hesap["brut"], "komisyon": f.komisyon - hesap["komisyon"],
                       "indirim+kupon": (f.ind + f.kup) - hesap["ind_kup"], "nakit": f.nakit - hesap["nakit"],
                       "kazanç": f.toplam_kazanc - beklenen}
            sorun = [k for k, v in farklar.items() if abs(v) > (0.5 if k == "kazanç" else 0.05)]
            rows.append({"bas": b, "bit": e, "fatura_no": f.fatura_no, "siparis": f.siparis, "siparis_h": hesap["siparis"],
                         "brut": f.brut, "brut_h": hesap["brut"], "komisyon": f.komisyon, "komisyon_h": hesap["komisyon"],
                         "cpc": f.cpc, "kazanc": f.toplam_kazanc, "kazanc_h": beklenen, "fark": round(f.toplam_kazanc - beklenen, 2),
                         "durum": "Tuttu" if not sorun else "Fark: " + ", ".join(sorun)})
        elif len(x):
            rows.append({"bas": b, "bit": e, "fatura_no": "", "siparis": np.nan, "siparis_h": hesap["siparis"],
                         "brut": np.nan, "brut_h": hesap["brut"], "komisyon": np.nan, "komisyon_h": hesap["komisyon"],
                         "cpc": np.nan, "kazanc": np.nan, "kazanc_h": hesap["kazanc"], "fark": np.nan, "durum": "Fatura özeti yok"})
    return pd.DataFrame(rows)


# ---- kampanyalar

def kampanyalar(a: Analiz, m: str) -> pd.DataFrame:
    k = a.kampanya
    if k.empty:
        return BOS
    k = _pencere(k[k["magaza"] == m].dropna(subset=["gun"]), a)
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["brut"] > 0)], a)
    rows = []
    for (p, ad), x in k.groupby(["platform", "kampanya"]):
        ilk, son = x["gun"].min(), x["gun"].max()
        ps = s[s["platform"] == p]
        ic = ps[(ps["gun"] >= ilk) & (ps["gun"] <= son)]
        kamp_sip = set(x["siparis"])
        diger = ic[~ic["siparis"].isin(kamp_sip)]
        siparis = x["siparis"].nunique()
        maliyet = x["maliyet"].sum()
        ciro = x.drop_duplicates("siparis")["brut"].sum()

        def gunluk(b, e):
            if b is None or e is None or e < b or (e - b).days + 1 < 7:
                return np.nan
            w = ps[(ps["gun"] >= b) & (ps["gun"] <= e)]
            return len(w) / ((e - b).days + 1)
        # mağaza bu platformda analiz başından sonra açıldıysa öncesi açılış gününden sayılır
        acilis = max(a.bas, ps["gun"].min()) if len(ps) else a.bas
        once = gunluk(acilis, ilk - timedelta(days=1))
        sira = gunluk(ilk, son)
        sonra = gunluk(son + timedelta(days=1), a.son)
        rows.append({"platform": p, "ad": ad, "ilk": ilk, "son": son, "aktif_gun": x["gun"].nunique(), "siparis": siparis,
                     "pay": siparis / len(ic) if len(ic) else np.nan, "maliyet": maliyet,
                     "platform_maliyet": x["platform_maliyet"].sum(), "siparis_basi": maliyet / siparis if siparis else np.nan,
                     "sepet_kamp": ciro / siparis if siparis else np.nan,
                     "sepet_diger": diger["brut"].mean() if len(diger) else np.nan,
                     "maliyet_orani": maliyet / ciro if ciro else np.nan,
                     "once": once, "sira": sira, "sonra": sonra})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    # Yemeksepeti'nde kampanya adı yok: işletmenin karşıladıkları ilk kullanım sırasıyla numaralanır
    t = t.sort_values(["platform", "ilk", "ad"]).reset_index(drop=True)
    t["anahtar"] = t["ad"]
    no = 0
    adlar = []
    for _, r in t.iterrows():
        if r.platform == YS and r.maliyet > 0:
            no += 1
            adlar.append(f"Kampanya {no} ({r.ad})")
        else:
            adlar.append(r.ad)
    t["ad"] = adlar
    return t


def kampanya_donem(a: Analiz, m: str) -> pd.DataFrame:
    """Dönem × platform: kampanyalı sipariş payı ve kampanya maliyetinin brüt satışa oranı."""
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["brut"] > 0)], a)
    rows = []
    for b, e in a.donemler:
        for p in platformlar(a, m):
            x = s[(s["platform"] == p) & (s["gun"] >= b) & (s["gun"] <= e)]
            rows.append({"bas": b, "bit": e, "platform": p, "siparis": len(x), "kampanyali": int((x["kampanya"] > 0).sum()),
                         "maliyet": x["kampanya"].sum(), "brut": x["brut"].sum()})
    return pd.DataFrame(rows)


# ---- müşteri algısı

def degerlendirmeler(a: Analiz, m: str) -> pd.DataFrame:
    parcalar = [d[d["magaza"] == m] for d in (a.ty_deg, a.ys_deg) if not d.empty]
    if not parcalar:
        return BOS
    d = pd.concat(parcalar, ignore_index=True)
    d["gun"] = d["zaman"].dt.date
    return d


def algi_donem(a: Analiz, m: str) -> pd.DataFrame:
    d = degerlendirmeler(a, m)
    d = _pencere(d, a) if not d.empty else d
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["brut"] > 0)], a)
    p = _pencere(a.ys_perf[a.ys_perf["magaza"] == m], a) if not a.ys_perf.empty else BOS
    rows = []
    for b, e in a.donemler:
        for pl in platformlar(a, m):
            x = d[(d["platform"] == pl) & (d["gun"] >= b) & (d["gun"] <= e)] if len(d) else BOS
            n_sip = int(((s["platform"] == pl) & (s["gun"] >= b) & (s["gun"] <= e)).sum())
            r = {"bas": b, "bit": e, "platform": pl, "siparis": n_sip, "adet": len(x),
                 "puan": x["puan"].mean() if len(x) else np.nan,
                 "dusuk": int((x["puan"] <= DUSUK_PUAN).sum()) if len(x) else 0,
                 "yorum": int((x["metin"] != "").sum()) if len(x) else 0,
                 "cevap": int((x["cevap"] != "").sum()) if len(x) else 0,
                 "lezzet": x["lezzet"].mean() if len(x) else np.nan, "servis": x["servis"].mean() if len(x) else np.nan,
                 "teslimat": x["teslimat"].mean() if len(x) else np.nan}
            if pl == YS and len(p):
                px = p[(p["gun"] >= b) & (p["gun"] <= e)]
                r.update({"yeni": px["yeni"].sum(), "donen": px["donen"].sum(), "iptal": px["isletme_iptal"].sum(),
                          "sikayet": px["sikayet"].sum(),
                          "hazirlama": (px["hazirlama"] * px["basarili"]).sum() / px["basarili"].sum() if px["basarili"].sum() else np.nan,
                          "kapali_oran": px["kapali_dk"].sum() / px["planli_dk"].sum() if px["planli_dk"].sum() else np.nan})
            rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- aylar, günler, reklam etkisi, ay ayrıntısı

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
INDIRIM_TOLERANSI = 5.0  # puan: indirim oranı bundan fazla farklı haftalardaki günler baza alınmaz
BAZ_HAFTA = 4  # tek günlük reklamın bazı: aynı haftagününün ±4 hafta içindeki reklamsız günleri
ONCE_GUN = 28  # sürekli reklamın bazı: başlamadan önceki 28 gün içindeki reklamsız günler


def ay_sonu(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def aylar(a: Analiz, m: str) -> pd.DataFrame:
    """Ay başına iki platformun toplamı; 'tam' sütunu ayın bütün günlerinin analizde olup olmadığını söyler."""
    t = toplam_trend(trend(a, m))
    if t.empty:
        return t
    y = aylik(t)
    y["tam"] = [b.day == 1 and s >= ay_sonu(b) for b, s in zip(y["bas"], y["bit"])]
    return y.sort_values("ay").reset_index(drop=True)


def gunluk(a: Analiz, m: str) -> pd.DataFrame:
    """Gün başına iki platformun siparişi, Trendyol reklam harcaması ve reklam türü (tekil / sürekli / boş)."""
    gunler = list(pd.date_range(a.bas, a.son).date)
    s = _pencere(a.siparis[a.siparis["magaza"] == m], a)
    d = pd.DataFrame(index=pd.Index(gunler, name="gun"))
    for p, k in ((TY, "ty"), (YS, "ys")):
        x = s[s["platform"] == p]
        d[f"{k}_siparis"] = x[x["brut"] > 0].groupby("gun").size().reindex(gunler).fillna(0).astype(int).values
        for c in ("brut", "kampanya", "kalan"):
            d[f"{k}_{c}"] = x.groupby("gun")[c].sum().reindex(gunler).fillna(0.0).values
    d["harcama"] = 0.0
    rg = ty_reklam_gunluk(a, m)
    d["maliyet"] = rg["maliyet"].reindex(gunler).fillna(0.0).values if len(rg) else 0.0
    d["tur"] = ""
    d["kampanya"] = ""
    r = a.ty_reklam[(a.ty_reklam["magaza"] == m) & (a.ty_reklam["harcama"] > 0)] if not a.ty_reklam.empty else BOS
    if len(r):
        d["harcama"] = r.groupby("gun")["harcama"].sum().reindex(gunler).fillna(0.0).values
        rk = a.ty_reklam_kampanya
        gun_sayisi = rk[rk["magaza"] == m].set_index("kampanya")["gun"].to_dict()
        for g_, x in r.groupby("gun"):
            if g_ in d.index:
                kamp = sorted(set(x["kampanya"]))
                d.at[g_, "kampanya"] = ", ".join(kamp)
                d.at[g_, "tur"] = "tekil" if all(gun_sayisi.get(k, 0) == 1 for k in kamp) else "sürekli"
    return d


def _ty_acilis(d: pd.DataFrame) -> date:
    """Mağazanın Trendyol'daki ilk siparişli günü: daha önceki boş günler baza alınmaz (mağaza henüz açık değildi)."""
    dolu = [g_ for g_ in d.index if d.at[g_, "ty_siparis"] > 0]
    return dolu[0] if dolu else d.index[0]


def _haftalik_indirim(d: pd.DataFrame) -> dict:
    """ISO hafta → Trendyol indirim oranı (puan)."""
    toplam: dict = {}
    for g_, r in d.iterrows():
        k = tuple(pd.Timestamp(g_).isocalendar()[:2])
        ind, brut = toplam.get(k, (0.0, 0.0))
        toplam[k] = (ind + r.ty_kampanya, brut + r.ty_brut)
    return {k: (i / b * 100 if b else np.nan) for k, (i, b) in toplam.items()}


def tekil_reklam(a: Analiz, m: str) -> pd.DataFrame:
    """Tek günlük Trendyol reklamları: o gün, aynı haftagününün reklamsız ve benzer indirimli günleriyle karşılaştırılır.
    Net etki = (restorana kalan − bazın kalanı) − reklam bedeli; yemek maliyeti dahil değil, kârın üst sınırıdır."""
    rk = a.ty_reklam_kampanya
    if rk.empty or a.ty_reklam.empty:
        return BOS
    d = gunluk(a, m)
    acilis = _ty_acilis(d)
    hafta = _haftalik_indirim(d)
    hk = lambda g_: hafta.get(tuple(pd.Timestamp(g_).isocalendar()[:2]), np.nan)  # noqa: E731
    s = _pencere(a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == TY) & (a.siparis["brut"] > 0)], a)
    r = a.ty_reklam[(a.ty_reklam["magaza"] == m) & (a.ty_reklam["harcama"] > 0)]
    rows = []
    for _, k in rk[(rk["magaza"] == m) & (rk["gun"] == 1)].iterrows():
        x = r[r["kampanya"] == k.kampanya]
        gun_ = x["gun"].min()
        if gun_ < a.bas or gun_ > a.son:
            continue
        harcama = x["harcama"].sum()
        aday = [gun_ + timedelta(days=7 * i) for i in range(-BAZ_HAFTA, BAZ_HAFTA + 1) if i]
        aday = [g_ for g_ in aday if acilis <= g_ <= a.son and d.at[g_, "harcama"] == 0]
        ref = hk(gun_)
        kars = [g_ for g_ in aday if pd.isna(ref) or abs(hk(g_) - ref) <= INDIRIM_TOLERANSI]
        notlar = []
        if len(aday) > len(kars):
            notlar.append(f"{len(aday) - len(kars)} gün farklı indirim döneminde olduğu için baza alınmadı")
        b = d.loc[kars] if kars else d.iloc[0:0]
        bas_t = pd.Timestamp(k.baslangic) if k.baslangic is not None and pd.notna(k.baslangic) else None
        saat = bas_t.time() if bas_t is not None and bas_t.date() == gun_ else None

        def sonra(g_):
            w = s[s["gun"] == g_]
            return int((w["zaman"].dt.time >= saat).sum()) if saat else np.nan
        baz_sip = b["ty_siparis"].mean() if len(b) else np.nan
        baz_kalan = b["ty_kalan"].mean() if len(b) else np.nan
        kalan_fark = d.at[gun_, "ty_kalan"] - baz_kalan
        maliyet = d.at[gun_, "maliyet"]  # restoranın payı; harcamanın bir bölümünü Trendyol karşılamış olabilir
        if len(kars) < 2:
            notlar.append("benzer indirim döneminde karşılaştırılabilir gün 2'den az: sonuç güvenilir değil")
        rows.append({"gun": gun_, "haftagunu": GUNLER[gun_.weekday()], "kampanya": k.kampanya, "saat": saat, "harcama": harcama,
                     "maliyet": maliyet, "siparis": int(d.at[gun_, "ty_siparis"]), "baz": baz_sip,
                     "baz_min": b["ty_siparis"].min() if len(b) else np.nan, "baz_max": b["ty_siparis"].max() if len(b) else np.nan,
                     "fark": d.at[gun_, "ty_siparis"] - baz_sip,
                     "basabas": maliyet / (baz_kalan / baz_sip) if baz_sip and baz_kalan and baz_sip > 0 else np.nan,
                     "kalan_fark": kalan_fark, "net": kalan_fark - maliyet,
                     "saat_sonra": sonra(gun_), "baz_saat_sonra": float(np.mean([sonra(g_) for g_ in kars])) if kars and saat else np.nan,
                     "karsilastirma": ", ".join(f"{g_.day:02d}.{g_.month:02d}" for g_ in kars),
                     "guvenilir": len(kars) >= 2, "not": "; ".join(notlar)})
    return pd.DataFrame(rows)


def surekli_reklam(a: Analiz, m: str) -> pd.DataFrame:
    """Art arda en az 3 gün süren Trendyol reklam dönemleri: dönem içi ile başlamadan önceki reklamsız günler karşılaştırılır."""
    if a.ty_reklam.empty:
        return BOS
    d = gunluk(a, m)
    gunler = [g_ for g_ in d.index if d.at[g_, "tur"] == "sürekli"]
    kosular, simdiki = [], []
    for g_ in gunler:
        if simdiki and (g_ - simdiki[-1]).days > 1:
            kosular.append(simdiki)
            simdiki = []
        simdiki.append(g_)
    if simdiki:
        kosular.append(simdiki)

    def olc(x):
        return {"gun": len(x), "siparis": x["ty_siparis"].mean() if len(x) else np.nan, "kalan": x["ty_kalan"].mean() if len(x) else np.nan,
                "indirim": x["ty_kampanya"].sum() / x["ty_brut"].sum() * 100 if len(x) and x["ty_brut"].sum() else np.nan,
                "harcama": x["harcama"].mean() if len(x) else np.nan, "maliyet": x["maliyet"].mean() if len(x) else np.nan}
    acilis = _ty_acilis(d)
    rows = []
    for k in kosular:
        if len(k) < 3:
            continue
        ic = d.loc[k]
        once_g = [g_ for g_ in d.index if max(acilis, k[0] - timedelta(days=ONCE_GUN)) <= g_ < k[0] and d.at[g_, "harcama"] == 0]
        once = olc(d.loc[once_g]) if once_g else olc(d.iloc[0:0])
        sira = olc(ic)
        net = (sira["kalan"] - once["kalan"]) - sira["maliyet"] if once["gun"] >= 5 else np.nan
        rows.append({"bas": k[0], "bit": k[-1], "kampanya": ", ".join(sorted(set(", ".join(ic["kampanya"]).split(", ")))),
                     "once": once, "sira": sira, "net": net,
                     "not": "" if once["gun"] >= 5 else "öncesinde karşılaştırmaya yetecek reklamsız gün yok (en az 5 gün gerekir)"})
    return pd.DataFrame(rows)


def ay_ayrintisi(a: Analiz, m: str, bas: date, son: date) -> dict:
    """Bir ayın saat, haftagünü, platform, ürün ve kampanya kırılımları."""
    s = a.siparis[(a.siparis["magaza"] == m) & (a.siparis["gun"] >= bas) & (a.siparis["gun"] <= son)]
    satis = s[s["brut"] > 0]
    plat = platformlar(a, m)
    sonuc = {}
    saat = satis.groupby([satis["zaman"].dt.hour, "platform"]).size().unstack(fill_value=0)
    sonuc["saat"] = saat.reindex(columns=plat, fill_value=0)
    gunler = pd.Series(pd.date_range(bas, son)).dt.weekday.value_counts()
    hg = satis.groupby([satis["zaman"].dt.weekday, "platform"]).size().unstack(fill_value=0).reindex(range(7), fill_value=0)
    sonuc["haftagunu"] = hg.reindex(columns=plat, fill_value=0).div(gunler.reindex(range(7)).replace(0, np.nan), axis=0)
    t = trend(a, m)
    t = t[(t["bas"] >= bas) & (t["bit"] <= son)].groupby("platform")[["siparis", "brut", "kampanya", "komisyon", "reklam", "diger",
                                                                          "iade", "kalan"]].sum()
    sonuc["platform"] = t.reindex(plat)
    u = a.urun
    if not u.empty:
        u = u[(u["magaza"] == m) & (u["gun"] >= bas) & (u["gun"] <= son)]
        sonuc["urun"] = u.groupby(["platform", "urun"], as_index=False).agg(adet=("adet", "sum"), ciro=("ciro", "sum"))
    k = a.kampanya
    if not k.empty:
        k = k[(k["magaza"] == m) & (k["gun"] >= bas) & (k["gun"] <= son)]
        adlar = kampanyalar(a, m)
        harita = dict(zip(zip(adlar["platform"], adlar["anahtar"]), adlar["ad"])) if not adlar.empty else {}
        kk = k.groupby(["platform", "kampanya"], as_index=False).agg(siparis=("siparis", "nunique"), maliyet=("maliyet", "sum"),
                                                                    platform_maliyet=("platform_maliyet", "sum"),
                                                                    ilk=("gun", "min"), son=("gun", "max"))
        kk["ad"] = [harita.get((p, n), n) for p, n in zip(kk["platform"], kk["kampanya"])]
        sonuc["kampanya"] = kk
    return sonuc


# ---------------------------------------------------------------- uyarılar

def _tl(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def _uyarilari_topla(a: Analiz) -> None:
    U = a.uyarilar
    if not a.ys_fatura.empty:
        x = a.ys_fatura[(a.ys_fatura["magaza"] == "") & (a.ys_fatura["bit"] >= a.bas) & (a.ys_fatura["bas"] <= a.son)]
        for _, r in x.iterrows():
            U.append(Uyari("", "hata", f"Yemeksepeti {etiket(r.bas, r.bit)} fatura özeti ({r.fatura_no}) hiçbir mağazanın siparişleriyle "
                           "eşleşmedi: sipariş sayısı ya da brüt satış tutmuyor, veya o dönemin sipariş listesi eksik."))
    for m in a.magazalar:
        for tur, ad in (("ty_online", "komisyon"), ("ty_kapida", "kapıda ödeme")):
            k = ty_komisyon_kontrol(a, m, tur)
            if k.empty:
                continue
            bozuk = k[k["durum"] != "Tuttu"]
            for durum, x in bozuk.groupby("durum"):
                U.append(Uyari(m, "hata" if "yok" in durum.lower() or "fark" in durum.lower() else "uyari",
                               f"Trendyol {ad} faturası: {len(x)} kayıtta “{durum}”."))
        if not a.ty_satir_sapma.empty:
            x = _pencere(a.ty_satir_sapma[a.ty_satir_sapma["magaza"] == m].assign(gun=lambda d: d["zaman"].dt.date), a)
            if len(x):
                U.append(Uyari(m, "uyari", f"Trendyol detayında {len(x)} satırda komisyon formülden sapıyor (toplam {_tl(x['fark'].sum())})."))
        rk = a.ty_reklam_kampanya
        if not rk.empty:
            x = rk[(rk["magaza"] == m) & (rk["son"] >= a.bas)]
            kapsamaz = x[x["durum"] == "Fatura listesi bu tarihi kapsamıyor"]
            if len(kapsamaz):
                U.append(Uyari(m, "bilgi", "Trendyol fatura listesi şu reklam kampanyalarının başladığı tarihi kapsamıyor: "
                               + ", ".join(kapsamaz["kampanya"]) + ". Daha eski tarihten indirilmiş liste gerekir."))
            x = x[x["durum"] != "Fatura listesi bu tarihi kapsamıyor"]
            trendyol = x[x["trendyol_payi"] > 0]
            fazla = x[x["durum"] == "Fatura harcamadan fazla"]
            parca = []
            if trendyol["trendyol_payi"].sum() > 50:
                ayrinti = [f"{r.kampanya} ({'tamamı' if r.fatura == 0 else 'bir bölümü'}, {_tl(r.trendyol_payi)})"
                           for r in trendyol.sort_values("ilk").itertuples()]
                parca.append(f"Bazı reklam kampanyalarında bedelin bir bölümünü ya da tamamını Trendyol karşıladı: toplam "
                             f"{_tl(trendyol['trendyol_payi'].sum())} ({', '.join(ayrinti)}).")
            if (fazla["fark"].sum()) > 50:
                ayrinti = [f"{r.kampanya} ({_tl(r.fark)})" for r in fazla.sort_values("ilk").itertuples()]
                parca.append(f"Şu kampanyalarda kesilen bedel harcamadan fazla, harcanmayan bütçe için iade faturası görünmüyor: "
                             f"{', '.join(ayrinti)}.")
            if parca:
                parca.append(f"Toplam reklam harcaması {_tl(x['harcama'].sum())}, restorana kesilen Reklam Bedeli "
                             f"{_tl(x['fatura'].sum())}. Raporda reklam maliyeti olarak restorana kesilen tutar kullanıldı.")
                U.append(Uyari(m, "bilgi", " ".join(parca)))
        if not a.ty_fatura.empty:
            f = a.ty_fatura[(a.ty_fatura["magaza"] == m)]
            f = f[(f["zaman"].dt.date >= a.bas) & (f["zaman"].dt.date <= a.son)]
            bilinmeyen = f[~f["tip"].isin(["Komisyon Faturası", "Kapıda Ödeme İşlemleri Komisyon Kesinti Faturası", "Reklam Bedeli"])]
            for tip, x in bilinmeyen.groupby("tip"):
                U.append(Uyari(m, "bilgi", f"Trendyol fatura listesinde incelenmeyen fatura türü: “{tip}” ({len(x)} adet, {_tl(x['tutar'].sum())})."))
        if platformlar(a, m).count(YS):
            k = ys_fatura_kontrol(a, m)
            yok = k[k["durum"] == "Fatura özeti yok"] if not k.empty else k
            if len(yok):
                U.append(Uyari(m, "hata", f"Yemeksepeti fatura özeti eksik: {len(yok)} dönem (reklam bedeli ve fatura kontrolü bu dönemlerde yapılamadı)."))
            fark = k[k["durum"].str.startswith("Fark")] if not k.empty else k
            for _, r in fark.iterrows():
                U.append(Uyari(m, "hata", f"Yemeksepeti {etiket(r.bas, r.bit)} faturası: {r.durum[6:]} tutmuyor."))
        if not a.ys_sapma.empty:
            x = _pencere(a.ys_sapma[a.ys_sapma["magaza"] == m], a)
            dus = x[x["neden"].str.contains("Kazanç beklenenden")]
            if len(dus):
                U.append(Uyari(m, "hata", f"Yemeksepeti'nde {len(dus)} siparişte kazanç beklenenden farklı (sipariş tutarı ödemeye yansımamış olabilir)."))
            ko = x[x["neden"].str.contains("Komisyon oranı") & ~x["neden"].str.contains("Kazanç")]
            if len(ko):
                U.append(Uyari(m, "uyari", f"Yemeksepeti'nde {len(ko)} siparişte komisyon oranı olağandan farklı."))
        s = a.siparis[(a.siparis["magaza"] == m)]
        bil = s[s["bilinmeyen"].abs() > 0]
        if len(bil):
            U.append(Uyari(m, "uyari", f"Trendyol detayında tanınmayan işlem tipi: {len(bil)} sipariş."))
