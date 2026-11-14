"""Girdi klasöründeki Trendyol Go ve Yemeksepeti dosyalarını tanır ve okur.

Dosya adına değil içeriğe bakılır: sayfa adı ve sütun başlıkları türü belirler.
Zip arşivlerinin içi de taranır. Birebir aynı dosyalar (sha256) bir kez okunur;
kayıt düzeyindeki kopyalar hesap.py'de ayıklanır (en yeni dosyadaki kayıt kalır).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

TUR_ADLARI = {
    "ty_online": "Trendyol komisyon fatura detayı",
    "ty_kapida": "Trendyol kapıda ödeme detayı",
    "ty_fatura": "Trendyol fatura listesi",
    "ty_reklam": "Trendyol reklam raporu",
    "ty_degerlendirme": "Trendyol değerlendirmeleri",
    "ys_siparis": "Yemeksepeti sipariş listesi",
    "ys_fatura": "Yemeksepeti fatura özeti",
    "ys_performans": "Yemeksepeti günlük performans",
    "ys_urun": "Yemeksepeti ürün satışları",
    "ys_degerlendirme": "Yemeksepeti değerlendirmeleri",
    "ty_gecmis": "Trendyol geçmiş siparişler (kullanılmıyor)",
}


@dataclass
class Dosya:
    ad: str
    veri: bytes
    zaman: float
    sha: str = ""

    def __post_init__(self):
        self.sha = hashlib.sha256(self.veri).hexdigest()


@dataclass
class Kayit:
    """Bir dosyanın tanınma sonucu (rapordaki veri kapsamı tablosu için)."""
    ad: str
    tur: str = ""
    satir: int = 0
    durum: str = ""


@dataclass
class Girdi:
    tablolar: dict = field(default_factory=dict)  # tür -> DataFrame (birleştirilmiş, _dosya/_zaman sütunlu)
    kayitlar: list = field(default_factory=list)


def _zip_ici(ad: str, veri: bytes, zaman: float, derinlik: int = 0):
    try:
        with zipfile.ZipFile(io.BytesIO(veri)) as z:
            for bilgi in z.infolist():
                if bilgi.is_dir():
                    continue
                ic = z.read(bilgi)
                try:
                    t = datetime(*bilgi.date_time).timestamp()
                except (ValueError, OverflowError):
                    t = zaman
                tam = f"{ad}/{bilgi.filename}"
                if bilgi.filename.lower().endswith(".zip") and derinlik < 2:
                    yield from _zip_ici(tam, ic, t, derinlik + 1)
                else:
                    yield Dosya(tam, ic, t)
    except zipfile.BadZipFile:
        yield Dosya(ad, veri, zaman)


def dosyalari_bul(klasor: str) -> list[Dosya]:
    sonuc = []
    for kok, _, adlar in os.walk(klasor):
        for a in sorted(adlar):
            yol = os.path.join(kok, a)
            with open(yol, "rb") as f:
                veri = f.read()
            ad = os.path.relpath(yol, klasor).replace("\\", "/")
            zaman = os.path.getmtime(yol)
            if a.lower().endswith(".zip"):
                sonuc.extend(_zip_ici(ad, veri, zaman))
            else:
                sonuc.append(Dosya(ad, veri, zaman))
    return sonuc


def _csv_oku(veri: bytes) -> pd.DataFrame:
    for kod in ("utf-8-sig", "cp1254"):
        try:
            metin = veri.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("karakter kodlaması çözülemedi")
    ilk = metin.split("\n", 1)[0]
    ayrac = ";" if ilk.count(";") > ilk.count(",") else ","
    return pd.read_csv(io.StringIO(metin), dtype=str, keep_default_na=False, sep=ayrac)


def _tur_bul(sutunlar: set, sayfa: str = "") -> str | None:
    s = sutunlar
    if {"İşlem Tipi", "Trendyol Hakediş", "Sipariş No"} <= s:
        return "ty_kapida" if "Satıcı İndirim" in s else "ty_online"
    if {"Fatura No", "Fatura Tipi", "Tutar"} <= s:
        return "ty_fatura"
    if {"Reklam Harcaması", "Gün"} <= s:
        return "ty_reklam"
    if {"Lezzet Puanı", "Ortalama Puan"} <= s:
        return "ty_degerlendirme"
    if {"Sipariş ürünleri", "Tahmini Kazanç"} <= s:
        return "ys_siparis"
    if {"Başlangıç Tarihi", "Bitiş Tarihi", "Toplam Kazanç"} <= s:
        return "ys_fatura"
    if {"Görüntülenme Sayısı", "Restoran No"} <= s:
        return "ys_performans"
    if {"Menü öğesi adı", "Satıcı Kimliği"} <= s:
        return "ys_urun"
    if {"İnceleme metni", "Puan"} <= s:
        return "ys_degerlendirme"
    if {"Platform tipi", "Sipariş Numarası"} <= s:
        return "ty_gecmis"
    return None


def _xlsx_oku(veri: bytes):
    # read_only kullanılmaz: Trendyol reklam dosyasının boyut etiketi yanlış ("A1"), salt-okur modda boş görünür
    sayfalar = pd.read_excel(io.BytesIO(veri), sheet_name=None, dtype=object)
    for sayfa, df in sayfalar.items():
        tur = _tur_bul(set(map(str, df.columns)), sayfa)
        if tur:
            return tur, df
    return None, None


def oku(klasor: str) -> Girdi:
    g = Girdi()
    gorulen: dict[str, str] = {}
    parcalar: dict[str, list] = {}
    for d in dosyalari_bul(klasor):
        k = Kayit(d.ad)
        g.kayitlar.append(k)
        if d.sha in gorulen:
            k.durum = f"kopya ({gorulen[d.sha]})"
            continue
        gorulen[d.sha] = d.ad
        alt = d.ad.lower()
        try:
            if alt.endswith(".xlsx"):
                tur, df = _xlsx_oku(d.veri)
            elif alt.endswith(".csv"):
                df = _csv_oku(d.veri)
                tur = _tur_bul(set(df.columns))
            else:
                k.durum = "tanınmadı (yalnızca .xlsx, .csv ve .zip okunur)"
                continue
        except Exception as e:  # bozuk dosya analizi durdurmasın
            k.durum = f"okunamadı: {str(e)[:120]}"
            continue
        if not tur:
            k.durum = "tanınmadı (sütunlar bilinen bir rapora uymuyor)"
            continue
        k.tur, k.satir = TUR_ADLARI[tur], len(df)
        if tur == "ty_gecmis":
            k.durum = "kullanılmıyor"
            continue
        k.durum = "okundu"
        df = df.copy()
        df["_dosya"], df["_zaman"], df["_sha"] = d.ad, d.zaman, d.sha
        if tur == "ty_degerlendirme":
            m = re.search(r"_(\d+)_De", os.path.basename(d.ad))
            df["_magaza_no"] = m.group(1) if m else ""
        if tur == "ty_reklam":
            m = re.match(r"Reklam-([0-9]{8}[A-Za-z]?)", os.path.basename(d.ad))
            df["_kampanya"] = m.group(1) if m else os.path.basename(d.ad)
        parcalar.setdefault(tur, []).append(df)
    for tur, ps in parcalar.items():
        g.tablolar[tur] = pd.concat(ps, ignore_index=True)
    return g


# ---- yardımcı dönüştürücüler ----

def sayi(x) -> float:
    """'1.364,00', '1364.00', '5,00', 12.5 ya da boş değeri sayıya çevirir."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return 0.0 if pd.isna(x) else float(x)
    s = str(x).strip().replace("₺", "").replace("TL", "").strip()
    if s in ("", "-", "nan", "NaN", "None"):
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def sayilar(seri: pd.Series) -> pd.Series:
    return seri.map(sayi).astype(float)


def tarih_tr(seri: pd.Series) -> pd.Series:
    """'31.10.2026 18:03' biçimi (Trendyol); Excel tarih nesnesi de olabilir."""
    s = pd.to_datetime(seri.astype(str).str.strip(), format="%d.%m.%Y %H:%M", errors="coerce")
    eksik = s.isna() & seri.notna()
    if eksik.any():
        s[eksik] = pd.to_datetime(seri[eksik], errors="coerce", dayfirst=True)
    return s


def tarih_iso(seri: pd.Series) -> pd.Series:
    s = pd.to_datetime(seri.astype(str).str.strip(), format="ISO8601", errors="coerce")
    eksik = s.isna() & (seri.astype(str).str.strip() != "")
    if eksik.any():
        s[eksik] = pd.to_datetime(seri[eksik], errors="coerce", dayfirst=True)
    return s
