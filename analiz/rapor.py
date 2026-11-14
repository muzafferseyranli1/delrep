"""Analiz sonuçlarından tek dosyalık HTML rapor üretir.

Sunucunun CSP'si dış kaynağa izin vermez: CSS, SVG grafikler ve küçük JS (sekmeler, ipucu) satır içidir.
Müşteri yorumları gibi dışarıdan gelen metinler her zaman kaçışlanır.
"""
from __future__ import annotations

import html
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

import hesap
from hesap import AY, AY_UZUN, TY, YS, etiket


# ---------------------------------------------------------------- biçimleme

class Ham(str):
    """Kaçışlanmayacak (bizim ürettiğimiz) HTML parçası."""


def e(x) -> str:
    return x if isinstance(x, Ham) else html.escape(str(x), quote=True)


def _bos(x) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) or x is pd.NaT


def sayi(x, ondalik=0) -> str:
    if _bos(x):
        return "—"
    s = f"{float(x):,.{ondalik}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tl(x, ondalik=0) -> str:
    s = sayi(x, ondalik)
    return s if s == "—" else s + " TL"


def yuzde(x, ondalik=1) -> str:
    return "—" if _bos(x) else "%" + sayi(x * 100, ondalik)


def gun(d) -> str:
    return "—" if _bos(d) or d is None else f"{d.day} {AY[d.month - 1]}"


def zaman(t) -> str:
    return "—" if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%d.%m.%Y %H:%M")


def oran(a, b):
    return a / b if b else np.nan


def degisim(yeni, eski) -> str:
    if _bos(yeni) or _bos(eski) or not eski:
        return ""
    d = yeni / eski - 1
    ok = "▲" if d > 0.005 else "▼" if d < -0.005 else "■"
    return f"{ok} {yuzde(abs(d), 0)}"


def tablo(basliklar, satirlar, sag=None, sinif="", alt=None) -> str:
    """sag: sağa yaslanacak sütun numaraları (sayılar). alt: toplam satırı."""
    sag = set(sag or [])
    h = ['<div class="tablo-kap"><table class="%s"><thead><tr>' % sinif]
    h += [f'<th class="{"r" if i in sag else ""}">{e(b)}</th>' for i, b in enumerate(basliklar)]
    h.append("</tr></thead><tbody>")
    for s in satirlar:
        h.append("<tr>" + "".join(f'<td class="{"r" if i in sag else ""}">{e(c)}</td>' for i, c in enumerate(s)) + "</tr>")
    h.append("</tbody>")
    if alt:
        h.append("<tfoot><tr>" + "".join(f'<td class="{"r" if i in sag else ""}">{e(c)}</td>' for i, c in enumerate(alt)) + "</tr></tfoot>")
    h.append("</table></div>")
    return "".join(h)


def rozet(durum: str) -> Ham:
    d = durum.lower()
    if d in ("tuttu", "tutuyor"):
        return Ham(f'<span class="rozet iyi">✓ {e(durum)}</span>')
    if "kapsamıyor" in d or d in ("harcama yok", "—"):
        return Ham(f'<span class="rozet notr">{e(durum)}</span>')
    if "yok" in d or "fark" in d or "bulunamadı" in d or "tutmuyor" in d or "faturadan fazla" in d:
        return Ham(f'<span class="rozet kotu">✕ {e(durum)}</span>')
    return Ham(f'<span class="rozet dikkat">! {e(durum)}</span>')


SEVIYE = {"hata": ("kotu", "✕", "Hata"), "uyari": ("dikkat", "!", "Uyarı"), "bilgi": ("notr", "i", "Bilgi")}


def uyari_listesi(uyarilar) -> str:
    if not uyarilar:
        return '<p class="tamam">✓ Kontrollerde sorun bulunmadı.</p>'
    sira = {"hata": 0, "uyari": 1, "bilgi": 2}
    h = ['<ul class="uyarilar">']
    for u in sorted(uyarilar, key=lambda u: sira[u.seviye]):
        s, i, ad = SEVIYE[u.seviye]
        h.append(f'<li class="{s}"><span class="ikon">{i}</span><b>{ad}:</b> {e(u.metin)}</li>')
    h.append("</ul>")
    return "".join(h)


def lejant(ogeler) -> str:
    return '<div class="lejant">' + "".join(
        f'<span><i style="background:var({r})"></i>{e(ad)}</span>' for ad, r in ogeler) + "</div>"


# ---------------------------------------------------------------- SVG grafikler

W, H = 720, 250
SOL, SAG, UST, ALT = 64, 96, 14, 34


def _guzel(maks: float):
    if not maks or maks <= 0 or _bos(maks):
        return 1.0, [0.0, 1.0]
    us = 10 ** math.floor(math.log10(maks))
    for c in (1, 2, 2.5, 5, 10):
        adim = c * us
        if maks / adim <= 5:
            break
    tepe = math.ceil(maks / adim - 1e-9) * adim
    return tepe, [i * adim for i in range(int(round(tepe / adim)) + 1)]


def _iskelet(etiketler, tepe, ticks, yfmt, her=1) -> list[str]:
    ph = H - UST - ALT
    n = len(etiketler)
    gw = (W - SOL - SAG) / max(n, 1)
    h = [f'<svg viewBox="0 0 {W} {H}" class="grafik" role="img">']
    for t in ticks:
        y = UST + ph * (1 - t / tepe)
        sinif = "taban" if t == 0 else "izgara"
        h.append(f'<line class="{sinif}" x1="{SOL}" x2="{W - SAG}" y1="{y:.1f}" y2="{y:.1f}"/>')
        h.append(f'<text class="eksen" x="{SOL - 8}" y="{y + 4:.1f}" text-anchor="end">{e(yfmt(t))}</text>')
    for i, et in enumerate(etiketler):
        if i % her == 0:
            x = SOL + gw * (i + 0.5)
            h.append(f'<text class="eksen" x="{x:.1f}" y="{H - 12}" text-anchor="middle">{e(et)}</text>')
    return h


def cizgi_grafik(etiketler, seriler, yfmt, ipucu_fmt=None) -> str:
    """seriler: [(ad, değerler, renk_değişkeni)]. Eksik değerler çizgide boşluk bırakır."""
    ipucu_fmt = ipucu_fmt or yfmt
    hepsi = [v for _, d, _ in seriler for v in d if not _bos(v)]
    if not hepsi:
        return ""
    tepe, ticks = _guzel(max(hepsi))
    ph = H - UST - ALT
    gw = (W - SOL - SAG) / len(etiketler)
    x = lambda i: SOL + gw * (i + 0.5)  # noqa: E731
    y = lambda v: UST + ph * (1 - v / tepe)  # noqa: E731
    h = _iskelet(etiketler, tepe, ticks, yfmt)
    son_y = []
    for ad, deg, renk in seriler:
        parca, yol = [], []
        for i, v in enumerate(deg):
            if _bos(v):
                if parca:
                    yol.append(parca)
                parca = []
            else:
                parca.append(f"{x(i):.1f},{y(v):.1f}")
        if parca:
            yol.append(parca)
        for p in yol:
            h.append(f'<polyline class="cizgi" style="stroke:var({renk})" points="{" ".join(p)}"/>')
        for i, v in enumerate(deg):
            if not _bos(v):
                h.append(f'<circle class="nokta" style="fill:var({renk})" cx="{x(i):.1f}" cy="{y(v):.1f}" r="4"/>')
                h.append(f'<circle class="isabet" cx="{x(i):.1f}" cy="{y(v):.1f}" r="13" data-t="{e(etiketler[i])} · {e(ad)}: {e(ipucu_fmt(v))}"/>')
        son = [(i, v) for i, v in enumerate(deg) if not _bos(v)]
        if son:
            i, v = son[-1]
            yy = y(v) + 4
            for o in son_y:
                if abs(o - yy) < 13:
                    yy = o + 13 if yy >= o else o - 13
            son_y.append(yy)
            h.append(f'<text class="dogrudan" x="{x(i) + 10:.1f}" y="{yy:.1f}">{e(ad)}</text>')
    h.append("</svg>")
    return "".join(h)


def _cubuk_yolu(x, y_ust, w, h, yuvarla=True) -> str:
    if h <= 0:
        return ""
    r = min(4, w / 2, h) if yuvarla else 0
    alt = y_ust + h
    if r <= 0:
        return f'M{x:.1f},{alt:.1f}V{y_ust:.1f}H{x + w:.1f}V{alt:.1f}Z'
    return (f'M{x:.1f},{alt:.1f}V{y_ust + r:.1f}Q{x:.1f},{y_ust:.1f} {x + r:.1f},{y_ust:.1f}'
            f'H{x + w - r:.1f}Q{x + w:.1f},{y_ust:.1f} {x + w:.1f},{y_ust + r:.1f}V{alt:.1f}Z')


def yigin_grafik(etiketler, katmanlar, yfmt) -> str:
    """katmanlar: alttan üste [(ad, değerler, renk)]. Negatif değerler 0 çizilir, ipucunda gerçek değer görünür."""
    n = len(etiketler)
    toplam = [sum(max(0.0, k[1][i] or 0.0) for k in katmanlar) for i in range(n)]
    tepe, ticks = _guzel(max(toplam) if toplam else 0)
    ph = H - UST - ALT
    gw = (W - SOL - SAG) / max(n, 1)
    bw = min(44, gw * 0.62)
    h = _iskelet(etiketler, tepe, ticks, yfmt)
    for i in range(n):
        x0 = SOL + gw * (i + 0.5) - bw / 2
        taban = UST + ph
        dolu = [(ad, max(0.0, d[i] or 0.0), d[i], r) for ad, d, r in katmanlar]
        dolu_var = [k for k in dolu if k[1] > 0]
        for j, (ad, v, gercek, renk) in enumerate(dolu_var):
            yh = ph * v / tepe
            ust = taban - yh
            bosluk = 2 if j < len(dolu_var) - 1 else 0
            yol = _cubuk_yolu(x0, ust + bosluk, bw, yh - bosluk, yuvarla=(j == len(dolu_var) - 1))
            pay = f" ({yuzde(oran(v, toplam[i]), 0)})" if toplam[i] else ""
            h.append(f'<path class="dilim" style="fill:var({renk})" d="{yol}" data-t="{e(etiketler[i])} · {e(ad)}: {e(yfmt(gercek))}{pay}"/>')
            taban = ust
    h.append("</svg>")
    return "".join(h)


def cubuk_grafik(etiketler, degerler, renkler, yfmt, ipuclari, her=7) -> str:
    n = len(etiketler)
    tepe, ticks = _guzel(max([v for v in degerler if not _bos(v)] or [0]))
    ph = H - UST - ALT
    gw = (W - SOL - SAG) / max(n, 1)
    bw = max(2.0, gw - 2)
    h = _iskelet(etiketler, tepe, ticks, yfmt, her=her)
    for i, v in enumerate(degerler):
        if _bos(v) or v <= 0:
            continue
        yh = ph * v / tepe
        x0 = SOL + gw * i + (gw - bw) / 2
        h.append(f'<path class="dilim" style="fill:var({renkler[i]})" d="{_cubuk_yolu(x0, UST + ph - yh, bw, yh)}" data-t="{e(ipuclari[i])}"/>')
    h.append("</svg>")
    return "".join(h)


def grafik_kutu(baslik, aciklama, govde, lej="") -> str:
    if not govde:
        return ""
    return f'<figure class="kart"><figcaption><b>{e(baslik)}</b><span>{e(aciklama)}</span></figcaption>{lej}{govde}</figure>'


# ---------------------------------------------------------------- bölümler

PLATFORM_RENK = {TY: "--s1", YS: "--s2"}


def _donem_et(r) -> str:
    return etiket(r["bas"], r["bit"])


def ozet_kutulari(a, m, tt) -> str:
    if tt.empty:
        return ""
    son, onceki = tt.iloc[-1], (tt.iloc[-2] if len(tt) > 1 else None)

    def kutu(baslik, deger, fmt, eski, puan=False):
        if puan and eski is not None and not _bos(deger) and not _bos(eski):
            d = (deger - eski) * 100
            alt = f"{'▲' if d > 0.05 else '▼' if d < -0.05 else '■'} {sayi(abs(d), 1)} puan"
        else:
            alt = degisim(deger, eski) if eski is not None else ""
        alt = f'<span class="degisim">{alt} önceki döneme göre</span>' if alt else ""
        return f'<div class="kutu"><span class="etiket">{e(baslik)}</span><span class="deger">{e(fmt(deger))}</span>{alt}</div>'

    g = son["gun"]
    og = onceki["gun"] if onceki is not None else None
    k = [
        kutu("Günlük sipariş", son["siparis"] / g, lambda v: sayi(v, 1), onceki["siparis"] / og if onceki is not None else None),
        kutu("Günlük brüt satış", son["brut"] / g, tl, onceki["brut"] / og if onceki is not None else None),
        kutu("Günlük restorana kalan", son["kalan"] / g, tl, onceki["kalan"] / og if onceki is not None else None),
        kutu("Restorana kalan oranı", oran(son["kalan"], son["brut"]), yuzde,
             oran(onceki["kalan"], onceki["brut"]) if onceki is not None else None, puan=True),
    ]
    return (f'<p class="alt-baslik">Son dönem: <b>{e(_donem_et(son))}</b> ({int(g)} gün), iki platform birlikte. '
            f'Kısa dönemler de karşılaştırılabilsin diye günlük ortalama.</p><div class="kutular">{"".join(k)}</div>')


def bolum_fatura(a, m) -> str:
    h = ['<h3>Trendyol Go</h3>']
    plat = hesap.platformlar(a, m)
    if TY in plat:
        k = hesap.ty_komisyon_kontrol(a, m, "ty_online")
        if not k.empty:
            satir = [[etiket(r.donem, min(hesap.donem_bit(r.donem), a.son)) if r.donem else "—", r.fatura_no or "—", zaman(r.fatura_tarihi),
                      tl(r.fatura, 2), tl(r.detay, 2), tl(r.fark, 2), rozet(r.durum)] for r in k.itertuples()]
            h.append("<h4>Haftalık komisyon faturaları</h4><p class='not'>Fatura listesindeki tutar, komisyon fatura detayındaki "
                     "satırların toplamıyla karşılaştırıldı.</p>")
            h.append(tablo(["Dönem", "Fatura no", "Fatura tarihi", "Fatura", "Detay toplamı", "Fark", "Durum"], satir, sag=[3, 4, 5],
                           alt=["Toplam", "", "", tl(k["fatura"].sum(), 2), tl(k["detay"].sum(), 2), "", ""]))
        k = hesap.ty_komisyon_kontrol(a, m, "ty_kapida")
        if not k.empty:
            iyi = (k["durum"] == "Tuttu").sum()
            h.append(f"<h4>Kapıda ödeme komisyon faturaları</h4><p class='not'>{len(k)} faturanın {iyi} tanesi detay dosyasıyla "
                     f"kuruşu kuruşuna tuttu. Toplam {tl(k['fatura'].sum(), 2)}.</p>")
            satir = [[etiket(r.donem, hesap.donem_bit(r.donem)) if r.donem else "—", r.fatura_no or "—", zaman(r.fatura_tarihi),
                      tl(r.fatura, 2), tl(r.detay, 2), rozet(r.durum)] for r in k.itertuples()]
            h.append("<details><summary>Faturaları göster</summary>" + tablo(
                ["Dönem", "Fatura no", "Fatura tarihi", "Fatura", "Detay", "Durum"], satir, sag=[3, 4]) + "</details>")
        sap = a.ty_satir_sapma
        if not sap.empty:
            x = sap[sap["magaza"] == m].assign(gun=lambda d: d["zaman"].dt.date)
            x = x[(x["gun"] >= a.bas) & (x["gun"] <= a.son)]
            if len(x):
                satir = [[zaman(r.zaman), r.siparis, r.urun[:60], sayi(r.oran, 1), tl(r.tutar, 2), tl(r.ty_hak, 2), tl(r.beklenen, 2)]
                         for r in x.head(30).itertuples()]
                h.append(f"<h4>Komisyon formülünden sapan satırlar ({len(x)})</h4>" + tablo(
                    ["Sipariş zamanı", "Sipariş", "Ürün", "Oran", "Tutar", "Kesilen", "Beklenen"], satir, sag=[3, 4, 5, 6]))
            else:
                h.append("<p class='not'>✓ Bütün satırlarda komisyon, tutar × komisyon oranına eşit (kuruş yuvarlaması dışında).</p>")
    rk = a.ty_reklam_kampanya
    if not rk.empty and (rk["magaza"] == m).any():
        x = rk[(rk["magaza"] == m) & (rk["son"] >= a.bas)]
        satir = [[r.kampanya, f"{gun(r.ilk)} – {gun(r.son)}", sayi(r.gun), tl(r.harcama, 2), tl(r.fatura, 2), int(r.fatura_adet),
                  tl(r.fark, 2), rozet(r.durum)] for r in x.itertuples()]
        h.append("<h4>Reklam Bedeli faturaları</h4><p class='not'>Her reklam kampanyasının harcaması (reklam raporu) ile kesilen "
                 "Reklam Bedeli faturaları. Günlük bütçeli kampanyalarda fatura her gün başında o günün bütçesi kadar kesiliyor; "
                 "bazı kampanyalar başlangıçta tek seferde faturalanıyor. Kampanyanın adı, başladığı gün ve saattir (GGAASSDD).</p>")
        h.append(tablo(["Kampanya", "Tarih", "Reklam günü", "Harcama", "Fatura", "Fatura adedi", "Fatura − harcama", "Durum"], satir,
                       sag=[2, 3, 4, 5, 6], alt=["Toplam", "", "", tl(x["harcama"].sum(), 2), tl(x["fatura"].sum(), 2),
                                                int(x["fatura_adet"].sum()), tl(x["fatura"].sum() - x["harcama"].sum(), 2), ""]))
    if TY not in plat and (rk.empty or not (rk["magaza"] == m).any()):
        h = []
    if YS in plat:
        h.append("<h3>Yemeksepeti</h3>")
        k = hesap.ys_fatura_kontrol(a, m)
        if not k.empty:
            satir = [[etiket(r.bas, r.bit), r.fatura_no or "—", f"{sayi(r.siparis)} / {sayi(r.siparis_h)}", tl(r.brut, 2),
                      tl(r.komisyon, 2), tl(r.cpc, 2), tl(r.kazanc, 2), tl(r.kazanc_h, 2), tl(r.fark, 2), rozet(r.durum)]
                     for r in k.itertuples()]
            h.append("<p class='not'>Fatura özetindeki her kalem sipariş listesinden yeniden hesaplandı: sipariş sayısı, brüt satış, "
                     "komisyon, işletme indirim ve kuponu, tahsil edilen nakit. Toplam kazanç = siparişlerin tahmini kazancı − "
                     "CPC reklam bedeli ve KDV'si.</p>")
            h.append(tablo(["Dönem", "Fatura no", "Sipariş (fatura / liste)", "Brüt satış", "Komisyon", "CPC reklam", "Toplam kazanç",
                            "Hesaplanan", "Fark", "Durum"], satir, sag=[3, 4, 5, 6, 7, 8]))
        if not a.ys_sapma.empty:
            x = a.ys_sapma[a.ys_sapma["magaza"] == m]
            x = x[(x["gun"] >= a.bas) & (x["gun"] <= a.son)]
            if len(x):
                satir = [[zaman(r.zaman), r.siparis, r.odeme, tl(r.brut, 2), tl(r.kampanya, 2), tl(r.ham_kom, 2), tl(r.kalan, 2), r.neden]
                         for r in x.itertuples()]
                h.append(f"<h4>Formülle tutmayan siparişler ({len(x)})</h4>" + tablo(
                    ["Sipariş zamanı", "Sipariş", "Ödeme", "Ara toplam", "İndirim+kupon", "Komisyon", "Tahmini kazanç", "Neden"],
                    satir, sag=[3, 4, 5, 6]))
    return "".join(h)


TREND_SUTUN = ["Dönem", "Platform", "Sipariş", "Sipariş/gün", "Brüt satış", "Ort. sepet", "Kampanya", "Komisyon", "Reklam",
               "Vergi ve diğer", "Restorana kalan", "Kalan %"]


def _trend_satiri(et, r):
    return [et, r["platform"], sayi(r["siparis"]), sayi(oran(r["siparis"], r["gun"]), 1), tl(r["brut"]),
            tl(oran(r["brut"], r["siparis"])), tl(r["kampanya"]), tl(r["komisyon"]), tl(r["reklam"]) + (" *" if r["reklam_eksik"] else ""),
            tl(r["diger"] + r["iade"]), tl(r["kalan"]), yuzde(oran(r["kalan"], r["brut"]))]


def bolum_trend(a, m, t, tt) -> str:
    if t.empty:
        return "<p>Veri yok.</p>"
    et = [etiket(b, s) for b, s in zip(tt["bas"], tt["bit"])]
    h = []
    seriler = []
    for p in hesap.platformlar(a, m):
        x = t[t["platform"] == p]
        seriler.append((p, list(x["siparis"] / x["gun"]), PLATFORM_RENK[p]))
    h.append(grafik_kutu("Günlük ortalama sipariş", "Fatura dönemine göre; 2–3 günlük ay sonu dönemleri de günlük ortalamayla karşılaştırılabilir.",
                         cizgi_grafik(et, seriler, lambda v: sayi(v, 0), lambda v: sayi(v, 1)),
                         lejant([(p, PLATFORM_RENK[p]) for p, _, _ in seriler])))
    katman = [("Restorana kalan", list(tt["kalan"] / tt["gun"]), "--s1"), ("Kampanya (indirim, kupon)", list(tt["kampanya"] / tt["gun"]), "--s2"),
              ("Komisyon", list(tt["komisyon"] / tt["gun"]), "--s3"), ("Reklam", list(tt["reklam"] / tt["gun"]), "--s4"),
              ("Vergi, iade ve diğer", list((tt["diger"] + tt["iade"]) / tt["gun"]), "--s5")]
    h.append(grafik_kutu("Günlük brüt satış nereye gidiyor", "İki platform birlikte, günlük ortalama TL. Çubuğun tamamı brüt satış.",
                         yigin_grafik(et, katman, lambda v: tl(v)), lejant([(k[0], k[2]) for k in katman])))
    satir = []
    for (b, s), x in t.groupby(["bas", "bit"], sort=True):
        for _, r in x.iterrows():
            satir.append(_trend_satiri(etiket(b, s), r))
        if len(x) > 1:
            r = tt[(tt["bas"] == b)].iloc[0]
            satir.append([Ham(f"<b>{e(etiket(b, s))}</b>"), Ham("<b>Toplam</b>")] + [Ham(f"<b>{e(c)}</b>") for c in _trend_satiri("", r)[2:]])
    h.append("<h4>Dönem dönem</h4>")
    h.append(tablo(TREND_SUTUN, satir, sag=list(range(2, 12))))
    ay = hesap.aylik(pd.concat([t, tt], ignore_index=True))
    if not ay.empty:
        satir = []
        ay = ay.assign(_sira=ay["platform"].map({TY: 0, YS: 1, "Toplam": 2})).sort_values(["ay", "_sira"])
        for _, r in ay.iterrows():
            yil, no = r["ay"]
            ay_sonu = hesap.donem_bit(r["bit"].replace(day=29)) if r["bit"].month != 2 or r["bit"].day >= 28 else r["bit"]
            tam = r["bas"].day == 1 and r["bit"] >= ay_sonu
            et_ay = f"{AY_UZUN[no - 1]} {yil}" + ("" if tam else f" ({gun(r['bas'])}–{gun(r['bit'])})")
            satir.append(_trend_satiri(et_ay, r))
        h.append("<h4>Aylık</h4>" + tablo(["Ay"] + TREND_SUTUN[1:], satir, sag=list(range(2, 12))))
    if t["reklam_eksik"].any():
        h.append("<p class='not'>* Yemeksepeti fatura özeti olmayan dönemlerde CPC reklam bedeli bilinmiyor; reklam ve restorana kalan bu "
                 "dönemlerde CPC'siz.</p>")
    h.append("<p class='not'>Kampanya: restoranın karşıladığı indirim ve kuponlar. Komisyon KDV dahil. Reklam: Trendyol'da reklam "
             "raporundaki harcama, Yemeksepeti'nde CPC bedeli + Joker reklam ücreti (KDV dahil). Vergi ve diğer: Yemeksepeti'nin online "
             "siparişlerde kestiği stopaj, iadeler ve formülle açıklanamayan farklar.</p>")
    return "".join(h)


def bolum_algi(a, m) -> str:
    d = hesap.algi_donem(a, m)
    if d.empty:
        return "<p>Veri yok.</p>"
    h = []
    satir = []
    for r in d.itertuples():
        satir.append([etiket(r.bas, r.bit), r.platform, sayi(r.adet), sayi(r.puan, 2) if r.adet else "—", sayi(r.dusuk),
                      sayi(r.yorum), sayi(r.cevap) if r.platform == TY else "—", yuzde(oran(r.adet, r.siparis), 0)])
    t = d.groupby("platform").agg(adet=("adet", "sum"), dusuk=("dusuk", "sum"), yorum=("yorum", "sum"), cevap=("cevap", "sum"),
                                  siparis=("siparis", "sum"))
    dg = hesap.degerlendirmeler(a, m)
    dg = dg[(dg["gun"] >= a.bas) & (dg["gun"] <= a.son)] if not dg.empty else dg
    ozet = []
    for p, r in t.iterrows():
        ort = dg[dg["platform"] == p]["puan"].mean() if not dg.empty else np.nan
        ozet.append(f"{p}: {sayi(r.adet)} değerlendirme, ortalama {sayi(ort, 2)}, {sayi(r.dusuk)} düşük puan")
    h.append(f"<p>{e('; '.join(ozet))}.</p>")
    h.append(f"<p class='not'>Değerlendirmeler sipariş tarihine göre döneme yazıldı. Düşük puan: {sayi(hesap.DUSUK_PUAN)} ve altı "
             "(5 üzerinden). Değerlendirme oranı: değerlendirme / sipariş.</p>")
    h.append(tablo(["Dönem", "Platform", "Değerlendirme", "Ort. puan", "Düşük puan", "Yorumlu", "Cevaplanan", "Değerlendirme oranı"],
                   satir, sag=[2, 3, 4, 5, 6, 7]))
    ty = d[(d["platform"] == TY) & (d["adet"] > 0)]
    if len(ty):
        satir = [[etiket(r.bas, r.bit), sayi(r.lezzet, 2), sayi(r.servis, 2), sayi(r.teslimat, 2)] for r in ty.itertuples()]
        h.append("<h4>Trendyol alt puanları</h4>" + tablo(["Dönem", "Lezzet", "Servis", "Teslimat"], satir, sag=[1, 2, 3]))
    ys = d[d["platform"] == YS]
    if len(ys) and "donen" in ys:
        satir = [[etiket(r.bas, r.bit), sayi(r.yeni), sayi(r.donen), yuzde(oran(r.donen, r.yeni + r.donen), 0), sayi(r.iptal),
                  sayi(r.sikayet), sayi(r.hazirlama, 1), yuzde(r.kapali_oran, 1)] for r in ys.itertuples()]
        h.append("<h4>Yemeksepeti müşteri davranışı</h4><p class='not'>Günlük performans raporundan. Dönen müşteri oranı sadakatin, "
                 "kapalı kalma oranı açık olunması planlanan sürede kapalı kalınan payın göstergesi.</p>")
        h.append(tablo(["Dönem", "Yeni müşteri siparişi", "Dönen müşteri siparişi", "Dönen oranı", "İşletme kaynaklı iptal", "Şikâyet",
                        "Ort. hazırlama (dk)", "Kapalı kalma"], satir, sag=list(range(1, 8))))
    if not dg.empty:
        tum = hesap.degerlendirmeler(a, m)
        dus = tum[tum["puan"] <= hesap.DUSUK_PUAN].sort_values("zaman", ascending=False)
        if len(dus):
            satir = [[zaman(r.zaman), r.platform, sayi(r.puan, 1), r.metin or "—", r.cevap or "—"] for r in dus.itertuples()]
            h.append(f"<h4>Düşük puanlı değerlendirmeler ({len(dus)}, en yenisi üstte)</h4>" + tablo(
                ["Sipariş", "Platform", "Puan", "Müşteri yorumu", "Restoran cevabı"], satir, sag=[2], sinif="metinli"))
        yor = tum[(tum["metin"] != "") & (tum["puan"] > hesap.DUSUK_PUAN)].sort_values("zaman", ascending=False).head(12)
        if len(yor):
            satir = [[zaman(r.zaman), r.platform, sayi(r.puan, 1), r.metin] for r in yor.itertuples()]
            h.append("<details><summary>Son olumlu yorumlar</summary>" + tablo(["Sipariş", "Platform", "Puan", "Yorum"], satir, sag=[2],
                                                                              sinif="metinli") + "</details>")
    return "".join(h)


def bolum_kampanya(a, m) -> str:
    k = hesap.kampanyalar(a, m)
    if k.empty:
        return "<p>Analiz döneminde restoranın karşıladığı indirim ya da kupon yok.</p>"
    h = ["<p class='not'>Kampanya: restoranın karşıladığı indirim ve kuponlar. Trendyol'da kampanya adı indirim satırından okunuyor. "
         "Yemeksepeti kampanya adı vermediği için indirim oranına ve kupon tutarına göre ayrılıp ilk kullanım sırasıyla numaralandı. "
         "“Günlük sipariş” sütunları o platformdaki bütün siparişlerin kampanyadan önce, kampanya süresince ve sonra günlük ortalaması "
         "(7 günden kısa aralık hesaplanmadı). Aynı dönemde başka kampanya ya da reklam değiştiyse fark yalnız bu kampanyaya ait değildir.</p>"]
    for p in (TY, YS):
        x = k[k["platform"] == p]
        if x.empty:
            continue
        satir = [[r.ad, f"{gun(r.ilk)} – {gun(r.son)}", sayi(r.aktif_gun), sayi(r.siparis), yuzde(r.pay, 0), tl(r.maliyet),
                  tl(r.siparis_basi), tl(r.sepet_kamp), tl(r.sepet_diger), sayi(r.once, 1), sayi(r.sira, 1), sayi(r.sonra, 1)]
                 for r in x.sort_values("maliyet", ascending=False).itertuples()]
        h.append(f"<h3>{e(p)}</h3>")
        enb = x.sort_values("maliyet", ascending=False).iloc[0]
        if enb.maliyet > 0:
            toplam = x["maliyet"].sum()
            cumle = (f"En büyük kampanya {enb.ad}: {sayi(enb.siparis)} siparişte {tl(enb.maliyet)}; toplam kampanya maliyetindeki "
                     f"payı {yuzde(oran(enb.maliyet, toplam), 0)}.")
            if not _bos(enb.once) and not _bos(enb.sira):
                cumle += f" Platformdaki günlük sipariş kampanyadan önce {sayi(enb.once, 1)}, kampanya süresince {sayi(enb.sira, 1)}."
            h.append(f"<p>{e(cumle)}</p>")
        h.append(tablo(["Kampanya", "Kullanım", "Aktif gün", "Sipariş", "Kampanyalı pay", "Maliyet", "Sipariş başı", "Sepet (kampanyalı)",
                        "Sepet (diğer)", "Günlük sipariş: önce", "sırasında", "sonra"], satir, sag=list(range(2, 12)),
                       alt=["Toplam", "", "", "", "", tl(x["maliyet"].sum()), "", "", "", "", "", ""]))
        pm = x["platform_maliyet"].sum()
        if pm > 0:
            h.append(f"<p class='not'>Platformun kendi karşıladığı indirim ve kuponlar (restorana maliyeti yok): {tl(pm)}.</p>")
    d = hesap.kampanya_donem(a, m)
    if not d.empty:
        satir = [[etiket(r.bas, r.bit), r.platform, sayi(r.siparis), yuzde(oran(r.kampanyali, r.siparis), 0), tl(r.maliyet),
                  yuzde(oran(r.maliyet, r.brut), 1)] for r in d.itertuples() if r.siparis]
        h.append("<h4>Dönem dönem kampanya yükü</h4>" + tablo(["Dönem", "Platform", "Sipariş", "Kampanyalı sipariş", "Kampanya maliyeti",
                                                                 "Maliyet / brüt satış"], satir, sag=[2, 3, 4, 5]))
    return "".join(h)


def bolum_reklam(a, m) -> str:
    h = ["<p class='not'>Reklam: platformda öne çıkmak için ödenen bedel (kampanyadan ayrı). Trendyol reklam raporu reklamdan gelen "
         "satışı veriyor; Yemeksepeti'nde reklam raporu yok, CPC bedeli fatura özetinden alınıp aynı dönemin görüntülenme ve sipariş "
         "sayılarıyla yan yana konuldu.</p>"]
    plat = hesap.platformlar(a, m)
    r = hesap.ty_reklam_donem(a, m)
    if TY in plat and not r.empty and r["harcama"].sum() > 0:
        h.append("<h3>Trendyol Go</h3>")
        satir = [[etiket(x.bas, x.bit), f"{x.reklam_gun}/{x.gun}", tl(x.harcama), sayi(x.gosterim), sayi(x.tiklama),
                  yuzde(oran(x.tiklama, x.gosterim), 1), sayi(x.satis), tl(x.ciro), sayi(oran(x.ciro, x.harcama), 1), sayi(x.yeni),
                  sayi(x.ty_siparis), yuzde(oran(x.satis, x.ty_siparis), 0)] for x in r.itertuples()]
        t = r.sum(numeric_only=True)
        h.append(tablo(["Dönem", "Reklamlı gün", "Harcama", "Gösterim", "Tıklama", "Tıklama oranı", "Reklamdan satış", "Reklam cirosu",
                        "Ciro / harcama", "Yeni müşteri", "Tüm Trendyol siparişi", "Reklamın payı"], satir, sag=list(range(1, 12)),
                       alt=["Toplam", f"{int(t.reklam_gun)}/{int(t.gun)}", tl(t.harcama), sayi(t.gosterim), sayi(t.tiklama),
                            yuzde(oran(t.tiklama, t.gosterim), 1), sayi(t.satis), tl(t.ciro), sayi(oran(t.ciro, t.harcama), 1),
                            sayi(t.yeni), sayi(t.ty_siparis), yuzde(oran(t.satis, t.ty_siparis), 0)]))
        g = hesap.ty_reklamli_gunler(a, m)
        if not g.empty and len(g) == 2:
            ev, ha = g.loc[True], g.loc[False]
            h.append(f"<p>Reklamlı {int(ev.gun)} günde Trendyol'da günlük ortalama <b>{e(sayi(ev.siparis, 1))}</b> sipariş "
                     f"({e(tl(ev.brut))} brüt), reklamsız {int(ha.gun)} günde <b>{e(sayi(ha.siparis, 1))}</b> sipariş ({e(tl(ha.brut))}). "
                     f"Reklamlı günlerde ortalama {e(tl(ev.harcama))} harcandı. Aradaki farkın bir kısmı aynı günlerdeki kampanyalardan "
                     f"ve mevsimden gelebilir; reklamın doğrudan payı için tablodaki “Reklamdan satış” sütununa bakın.</p>")
        s = a.siparis[(a.siparis["magaza"] == m) & (a.siparis["platform"] == TY) & (a.siparis["brut"] > 0)]
        gunler = list(pd.date_range(a.bas, a.son).date)
        adet = s.groupby("gun").size().reindex(gunler).fillna(0)
        har = a.ty_reklam[a.ty_reklam["magaza"] == m].groupby("gun")["harcama"].sum().reindex(gunler).fillna(0)
        renk = ["--s1" if v > 0 else "--notr" for v in har]
        ip = [f"{d.day} {AY[d.month - 1]}: {int(adet[d])} sipariş" + (f", reklam {tl(har[d])}" if har[d] > 0 else ", reklam yok") for d in gunler]
        h.append(grafik_kutu("Trendyol'da günlük sipariş", "Mavi çubuklar reklamlı, gri çubuklar reklamsız günler.",
                             cubuk_grafik([f"{d.day} {AY[d.month - 1]}" for d in gunler], list(adet), renk, lambda v: sayi(v), ip),
                             lejant([("Reklamlı gün", "--s1"), ("Reklamsız gün", "--notr")])))
    if YS in plat:
        y = hesap.ys_reklam_donem(a, m)
        if not y.empty:
            h.append("<h3>Yemeksepeti</h3>")
            satir = [[etiket(x.bas, x.bit), tl(x.cpc), tl(x.joker) + (f" ({x.joker_siparis})" if x.joker_siparis else ""),
                      sayi(oran(x.goruntulenme, x.gun)), sayi(oran(x.menu, x.gun)), yuzde(oran(x.menu, x.goruntulenme), 1),
                      sayi(x.sepet), sayi(x.siparis), yuzde(oran(x.siparis, x.menu), 1), tl(oran(x.cpc, x.siparis), 1)]
                     for x in y.itertuples()]
            h.append(tablo(["Dönem", "CPC (KDV dahil)", "Joker reklam ücreti", "Görüntülenme/gün", "Menü görüntüleme/gün", "Menüye geçiş",
                            "Sepete eklenen", "Sipariş", "Menüden siparişe", "Sipariş başına CPC"], satir, sag=list(range(1, 10))))
            yy = y.dropna(subset=["cpc", "goruntulenme"])
            if len(yy) >= 3:
                yy = yy.assign(cpc_gun=yy["cpc"] / yy["gun"], gor_gun=yy["goruntulenme"] / yy["gun"])
                dus, yuk = yy.nsmallest(1, "cpc_gun").iloc[0], yy.drop(yy.nsmallest(1, "cpc_gun").index)
                h.append(f"<p>CPC'nin en düşük olduğu dönemde ({e(etiket(dus.bas, dus.bit))}, günde {e(tl(dus.cpc_gun))}) günlük görüntülenme "
                         f"{e(sayi(dus.gor_gun))}; diğer dönemlerin ortalaması günde {e(tl(yuk['cpc_gun'].mean()))} CPC ile "
                         f"{e(sayi(yuk['gor_gun'].mean()))} görüntülenme.</p>")
            elif y["cpc"].isna().all():
                h.append("<p class='not'>Bu mağazanın Yemeksepeti fatura özeti olmadığı için CPC bedeli bilinmiyor.</p>")
    return "".join(h)


def bolum_veri(a, g) -> str:
    uc = a.kapsam["uclar"]
    h = [f"<p>Analiz aralığı: <b>{e(gun(a.bas))} {a.bas.year} – {e(gun(a.son))} {a.son.year}</b>. Aralık, iki platformun da tam verisinin "
         "bulunduğu son fatura dönemiyle bitiyor. Eldeki son tam gün: "
         + ", ".join(f"{e(p)} {e(gun(d))}" for p, d in uc.items())
         + ". Trendyol siparişleri haftalık komisyon faturasıyla geldiği için bir sonraki fatura kesilince sonraki dönem eklenecek.</p>"]
    h.append("<h4>Tanımlar</h4><ul class='tanimlar'>"
             "<li><b>Dönem:</b> platformların fatura dönemi — ayın 1–7, 8–14, 15–21, 22–28 ve 29–son günleri.</li>"
             "<li><b>Brüt satış:</b> menü fiyatıyla sipariş tutarı (indirimlerden önce).</li>"
             "<li><b>Kampanya:</b> restoranın karşıladığı indirim ve kuponlar. Platformun karşıladıkları ayrıca belirtildi.</li>"
             "<li><b>Komisyon:</b> KDV dahil. Trendyol'un %13,8'i KDV dahil oran; Yemeksepeti komisyonuna %20 KDV eklendi.</li>"
             "<li><b>Reklam:</b> öne çıkma bedeli. Trendyol reklam raporu harcaması; Yemeksepeti CPC bedeli ve Joker reklam ücreti, KDV dahil.</li>"
             "<li><b>Restorana kalan:</b> brüt satıştan kampanya, komisyon, reklam, vergi kesintileri ve iadeler düşüldükten sonra kalan.</li>"
             "</ul>")
    satir = [[k.ad, k.tur or "—", sayi(k.satir) if k.satir else "—", k.durum] for k in g.kayitlar]
    h.append(f"<h4>Okunan dosyalar ({len(g.kayitlar)})</h4>" + tablo(["Dosya", "Tür", "Satır", "Durum"], satir, sag=[2], sinif="metinli"))
    return "".join(h)


# ---------------------------------------------------------------- sayfa

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--yuzey:#fcfcfb;--kart:#ffffff;--murekkep:#0b0b0b;--ikincil:#52514e;--soluk:#898781;
--izgara:#e1e0d9;--taban:#c3c2b7;--cizgi:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;
--notr:#c3c2b7;--iyi:#006300;--iyi-z:#e5f3e5;--kotu:#d03b3b;--kotu-z:#fbe9e9;--dikkat:#8a5a00;--dikkat-z:#fdf3dc;--notr-z:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--yuzey:#1a1a19;--kart:#161615;
--murekkep:#f0efec;--ikincil:#c3c2b7;--soluk:#898781;--izgara:#2c2c2a;--taban:#383835;--cizgi:rgba(255,255,255,.10);--s1:#3987e5;
--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--notr:#4a4a47;--iyi:#0ca30c;--iyi-z:#14270f;--kotu:#e66767;--kotu-z:#2e1616;
--dikkat:#fab219;--dikkat-z:#2b2410;--notr-z:#232321}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--yuzey:#1a1a19;--kart:#161615;--murekkep:#f0efec;--ikincil:#c3c2b7;
--soluk:#898781;--izgara:#2c2c2a;--taban:#383835;--cizgi:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;
--s5:#d55181;--notr:#4a4a47;--iyi:#0ca30c;--iyi-z:#14270f;--kotu:#e66767;--kotu-z:#2e1616;--dikkat:#fab219;--dikkat-z:#2b2410;--notr-z:#232321}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--murekkep);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.sayfa{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
header h1{font-size:24px;margin:0 0 4px}
header p{margin:0;color:var(--ikincil)}
h2{font-size:20px;margin:36px 0 10px;padding-top:8px;border-top:1px solid var(--cizgi)}
h3{font-size:17px;margin:24px 0 8px}
h4{font-size:15px;margin:20px 0 6px}
p{margin:8px 0;max-width:80ch}
.not{color:var(--ikincil);font-size:13.5px}
.alt-baslik{color:var(--ikincil);font-size:14px}
nav.sekmeler{display:flex;flex-wrap:wrap;gap:6px;margin:20px 0 8px;position:sticky;top:0;background:var(--page);padding:8px 0;z-index:2}
nav.sekmeler button{font:inherit;padding:7px 14px;border-radius:8px;border:1px solid var(--cizgi);background:var(--kart);color:var(--murekkep);cursor:pointer}
nav.sekmeler button[aria-selected="true"]{background:var(--murekkep);color:var(--page);border-color:var(--murekkep)}
.icindekiler{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:14px;margin:6px 0 0}
.icindekiler a{color:var(--ikincil)}
.kutular{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:10px 0}
.kutu{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.kutu .etiket{font-size:13px;color:var(--ikincil)}
.kutu .deger{font-size:24px;font-weight:600}
.kutu .degisim{font-size:12.5px;color:var(--ikincil)}
.tablo-kap{overflow-x:auto;margin:8px 0 12px;border:1px solid var(--cizgi);border-radius:10px;background:var(--kart)}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid var(--cizgi);white-space:nowrap;vertical-align:top}
th{font-weight:600;color:var(--ikincil);background:var(--yuzey);position:sticky;top:0}
td.r,th.r{text-align:right}
tfoot td{font-weight:600;background:var(--yuzey)}
tbody tr:last-child td{border-bottom:none}
table.metinli td{white-space:normal;min-width:90px}
table.metinli td:nth-child(4),table.metinli td:nth-child(5){min-width:260px}
.rozet{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12.5px;font-weight:500}
.rozet.iyi{background:var(--iyi-z);color:var(--iyi)}.rozet.kotu{background:var(--kotu-z);color:var(--kotu)}
.rozet.dikkat{background:var(--dikkat-z);color:var(--dikkat)}.rozet.notr{background:var(--notr-z);color:var(--ikincil)}
ul.uyarilar{list-style:none;padding:0;margin:8px 0;display:flex;flex-direction:column;gap:6px}
ul.uyarilar li{padding:8px 12px 8px 38px;border-radius:8px;position:relative;font-size:14px;max-width:110ch}
ul.uyarilar li .ikon{position:absolute;left:12px;top:8px;width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;
justify-content:center;font-size:11px;font-weight:700;color:#fff}
li.kotu{background:var(--kotu-z)}li.kotu .ikon{background:var(--kotu)}
li.dikkat{background:var(--dikkat-z)}li.dikkat .ikon{background:#fab219;color:#0b0b0b}
li.notr{background:var(--notr-z)}li.notr .ikon{background:var(--soluk)}
.tamam{color:var(--iyi)}
figure.kart{margin:12px 0;background:var(--yuzey);border:1px solid var(--cizgi);border-radius:10px;padding:12px 14px}
figcaption{display:flex;flex-direction:column;gap:2px;margin-bottom:6px}
figcaption span{color:var(--ikincil);font-size:13px}
.lejant{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:13px;color:var(--ikincil);margin:4px 0 2px}
.lejant i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
svg.grafik{width:100%;height:auto;display:block;overflow:visible}
svg .izgara{stroke:var(--izgara);stroke-width:1}
svg .taban{stroke:var(--taban);stroke-width:1}
svg .eksen{fill:var(--soluk);font-size:11px;font-variant-numeric:tabular-nums}
svg .dogrudan{fill:var(--ikincil);font-size:12px}
svg .cizgi{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
svg .nokta{stroke:var(--yuzey);stroke-width:2}
svg .isabet{fill:transparent;cursor:default}
svg .dilim:hover,svg .isabet:hover{opacity:.85}
details{margin:6px 0 12px}
summary{cursor:pointer;color:var(--ikincil);font-size:14px}
ul.tanimlar{padding-left:20px;max-width:90ch}
#ipucu{position:fixed;pointer-events:none;background:var(--murekkep);color:var(--page);padding:5px 9px;border-radius:6px;font-size:12.5px;
z-index:10;max-width:320px;box-shadow:0 2px 8px rgba(0,0,0,.18)}
@media print{nav.sekmeler{display:none}section[data-panel]{display:block!important}}
"""

JS = """
(function(){
var b=[].slice.call(document.querySelectorAll('[data-sekme]')),p=[].slice.call(document.querySelectorAll('[data-panel]'));
function g(id){b.forEach(function(x){x.setAttribute('aria-selected',x.dataset.sekme===id?'true':'false')});
p.forEach(function(x){x.hidden=x.dataset.panel!==id});try{localStorage.setItem('paketrapor-sekme',id)}catch(e){}}
b.forEach(function(x){x.addEventListener('click',function(){g(x.dataset.sekme)})});
var s=null;try{s=localStorage.getItem('paketrapor-sekme')}catch(e){}
g(b.some(function(x){return x.dataset.sekme===s})?s:(b[0]&&b[0].dataset.sekme));
var t=document.getElementById('ipucu');
function k(ev){var h=ev.target.closest&&ev.target.closest('[data-t]');if(!h){t.hidden=true;return}
t.textContent=h.getAttribute('data-t');t.hidden=false;var x=ev.clientX+14,y=ev.clientY+14,w=t.offsetWidth,hh=t.offsetHeight;
if(x+w>innerWidth-8)x=ev.clientX-w-14;if(y+hh>innerHeight-8)y=ev.clientY-hh-14;t.style.left=x+'px';t.style.top=y+'px'}
document.addEventListener('mousemove',k);document.addEventListener('click',k);
})();
"""


def uret(a, g, olusturma: datetime | None = None) -> str:
    olusturma = olusturma or datetime.now()
    sekmeler, paneller, genel = [], [], []
    for i, m in enumerate(a.magazalar):
        sid = f"m{i}"
        t = hesap.trend(a, m)
        tt = hesap.toplam_trend(t)
        uy = [u for u in a.uyarilar if u.magaza == m]
        plat = hesap.platformlar(a, m)
        if not tt.empty:
            genel.append([m, ", ".join(plat), sayi(tt["siparis"].sum()), tl(tt["brut"].sum()), tl(tt["kampanya"].sum()),
                          tl(tt["komisyon"].sum()), tl(tt["reklam"].sum()), tl(tt["kalan"].sum()), yuzde(oran(tt["kalan"].sum(), tt["brut"].sum())),
                          Ham(f'<span class="rozet {"kotu" if any(u.seviye == "hata" for u in uy) else "iyi"}">'
                              f'{sum(u.seviye == "hata" for u in uy)} hata, {sum(u.seviye == "uyari" for u in uy)} uyarı</span>')])
        bolumler = [("fatura", "1. Fatura kontrolü", bolum_fatura(a, m)), ("trend", "2. Trend", bolum_trend(a, m, t, tt)),
                    ("algi", "3. Müşteri algısı", bolum_algi(a, m)), ("kampanya", "4. Kampanyaların etkisi", bolum_kampanya(a, m)),
                    ("reklam", "5. Reklamların etkisi", bolum_reklam(a, m))]
        ic = '<div class="icindekiler">' + "".join(f'<a href="#{sid}-{k}">{e(b)}</a>' for k, b, _ in bolumler) + "</div>"
        govde = "".join(f'<h2 id="{sid}-{k}">{e(b)}</h2>{h}' for k, b, h in bolumler)
        sekmeler.append(f'<button type="button" data-sekme="{sid}" aria-selected="false">{e(m)}</button>')
        paneller.append(f'<section data-panel="{sid}"><h2 style="border:none;margin-top:8px">{e(m)}</h2>'
                        f'<p class="alt-baslik">{e(" ve ".join(plat))}</p>{ic}{ozet_kutulari(a, m, tt)}'
                        f'<h4>Kontrol sonuçları</h4>{uyari_listesi(uy)}{govde}</section>')
    sekmeler.append('<button type="button" data-sekme="veri" aria-selected="false">Veri ve tanımlar</button>')
    paneller.append(f'<section data-panel="veri"><h2 style="border:none;margin-top:8px">Veri ve tanımlar</h2>{bolum_veri(a, g)}</section>')
    ortak = [u for u in a.uyarilar if not u.magaza]
    ozet = tablo(["Mağaza", "Platform", "Sipariş", "Brüt satış", "Kampanya", "Komisyon", "Reklam", "Restorana kalan", "Kalan %", "Kontroller"],
                 genel, sag=[2, 3, 4, 5, 6, 7, 8]) if genel else ""
    aralik = f"{a.bas.day} {AY_UZUN[a.bas.month - 1]} – {a.son.day} {AY_UZUN[a.son.month - 1]} {a.son.year}"
    return ("<!doctype html><html lang='tr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Paket servis raporu</title><style>{CSS}</style></head><body><div class='sayfa'>"
            f"<header><h1>Paket servis raporu</h1><p>{e(aralik)} · fatura kontrolü, trend, müşteri algısı, kampanya ve reklam etkisi · "
            f"oluşturuldu {e(olusturma.strftime('%d.%m.%Y %H:%M'))}</p></header>"
            f"{uyari_listesi(ortak) if ortak else ''}<h4>Mağazalar, analiz aralığının tamamı</h4>{ozet}"
            f"<nav class='sekmeler' aria-label='Mağazalar'>{''.join(sekmeler)}</nav>{''.join(paneller)}"
            f"</div><div id='ipucu' hidden></div><script>{JS}</script></body></html>")
