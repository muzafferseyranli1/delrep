"""
Analiz CSV'lerinden tek dosyalık HTML rapor üretir.
Dış kaynak ve betik yok: grafikler satır içi SVG, stiller satır içi (sunucudaki CSP buna göre sıkı).
"""
import csv
import html
import os
from collections import defaultdict
from datetime import datetime


def oku(cikti, ad):
    yol = os.path.join(cikti, ad)
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def sayi(v, varsayilan=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return varsayilan


def tr(v, ondalik=0):
    """1234567.8 -> '1.234.568' (Türkçe: nokta binlik, virgül ondalık)."""
    s = f"{sayi(v):,.{ondalik}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def tl(v, ondalik=0):
    return f"{tr(v, ondalik)} ₺"


def yuzde(v, ondalik=1):
    return f"%{tr(v, ondalik)}"


def e(s):
    return html.escape(str(s))


def yatay_grafik(etiketler, degerler, metinler, renkler=None):
    if not degerler:
        return '<p class="bos">Veri yok</p>'
    en = max(max(degerler), 1e-9)
    satir, w, sol, sag = 30, 680, 170, 110
    h = satir * len(degerler) + 4
    ps = [f'<svg viewBox="0 0 {w} {h}" class="grf" role="img">']
    for i, (et, d, m) in enumerate(zip(etiketler, degerler, metinler)):
        y = i * satir + 2
        bw = max(0.0, (w - sol - sag) * d / en)
        renk = renkler[i] if renkler else "var(--c1)"
        ps.append(
            f'<text x="{sol - 8}" y="{y + 19}" text-anchor="end" class="et">{e(et)}</text>'
            f'<rect x="{sol}" y="{y + 5}" width="{bw:.1f}" height="{satir - 11}" rx="3" fill="{renk}"/>'
            f'<text x="{sol + bw + 6:.1f}" y="{y + 19}" class="dg">{e(m)}</text>'
        )
    ps.append("</svg>")
    return "".join(ps)


def dikey_grafik(etiketler, degerler, deger_metni=None, etiket_aralik=1):
    if not degerler:
        return '<p class="bos">Veri yok</p>'
    w, h, ust, alt = 680, 230, 22, 34
    n = len(degerler)
    en = max(max(degerler), 1e-9)
    kutu = (w - 20) / n
    bw = max(2.0, kutu * 0.7)
    ps = [f'<svg viewBox="0 0 {w} {h}" class="grf" role="img">']
    for i, (et, d) in enumerate(zip(etiketler, degerler)):
        bh = (h - ust - alt) * d / en
        x = 10 + i * kutu + (kutu - bw) / 2
        y = h - alt - bh
        ps.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="var(--c1)"/>')
        if n <= 14 and deger_metni:
            ps.append(f'<text x="{x + bw / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="dg">{e(deger_metni(d))}</text>')
        if i % etiket_aralik == 0:
            ps.append(f'<text x="{x + bw / 2:.1f}" y="{h - 16}" text-anchor="middle" class="et">{e(et)}</text>')
    ps.append("</svg>")
    return "".join(ps)


def tablo(basliklar, satirlar, sag_kolonlar=()):
    if not satirlar:
        return '<p class="bos">Veri yok</p>'
    th = "".join(f'<th class="{"sag" if i in sag_kolonlar else ""}">{e(b)}</th>' for i, b in enumerate(basliklar))
    tr_ = "".join(
        "<tr>" + "".join(f'<td class="{"sag" if i in sag_kolonlar else ""}">{e(h)}</td>' for i, h in enumerate(s)) + "</tr>"
        for s in satirlar
    )
    return f'<div class="kaydir"><table><thead><tr>{th}</tr></thead><tbody>{tr_}</tbody></table></div>'


def kpi(baslik, deger, alt=""):
    return f'<div class="kpi"><div class="kb">{e(baslik)}</div><div class="kd">{e(deger)}</div><div class="ka">{e(alt)}</div></div>'


def aylik(cikti):
    """siparisler.csv'den ay bazlı özet: ay, sipariş, brüt, indirim oranı, hakediş."""
    ay = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for r in oku(cikti, "siparisler.csv"):
        a = ay[(r.get("t") or "")[:7]]
        a[0] += 1
        a[1] += sayi(r.get("brut"))
        a[2] += sayi(r.get("ind"))
        a[3] += sayi(r.get("sh"))
    satirlar = []
    for anahtar in sorted(k for k in ay if k):
        n, brut, ind, sh = ay[anahtar]
        yil, ayno = anahtar.split("-")
        satirlar.append((f"{ayno}.{yil}", tr(n), tl(brut), yuzde(ind / brut * 100 if brut else 0), tl(sh), tl(brut / n if n else 0)))
    return satirlar


CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--yazi:#1c2026;--soluk:#68707c;--cizgi:#dde1e7;--c1:#2f5fd0;--c2:#d9822b;--iyi:#1c7a43;--kotu:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#14171b;--kart:#1d2228;--yazi:#e8ebef;--soluk:#97a0ac;--cizgi:#303741;--c1:#6d96f0;--c2:#e8a05a;--iyi:#58c486;--kotu:#f08c85}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--yazi);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:20px 16px 56px}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;margin-bottom:16px}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:0 0 10px}.alt{color:var(--soluk);font-size:14px}
a{color:var(--c1)}.bosluk{flex:1}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:16px;margin-bottom:16px}
.kpiler{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:12px 14px}
.kb{color:var(--soluk);font-size:13px}.kd{font-size:22px;font-weight:650;margin:2px 0}.ka{color:var(--soluk);font-size:13px}
.grf{width:100%;height:auto;display:block}.et{font-size:12px;fill:var(--soluk)}.dg{font-size:12px;fill:var(--yazi)}
.kaydir{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--cizgi)}th{color:var(--soluk);font-weight:600;white-space:nowrap}
td.sag,th.sag{text-align:right;white-space:nowrap}.bos{color:var(--soluk)}
.not{border-left:3px solid var(--c2);padding:6px 12px;margin-bottom:16px;color:var(--soluk);font-size:14px}
@media (max-width:560px){.kd{font-size:19px}}
"""


def uret(cikti, dosya_sayisi, taninmayan, aralik):
    ozet = (oku(cikti, "ozet.csv") or [{}])[0]
    akis = oku(cikti, "akis.csv")
    platform = oku(cikti, "platform.csv")
    donem = oku(cikti, "donem.csv")
    gunluk = oku(cikti, "gunluk.csv")
    saat = oku(cikti, "saat.csv")
    haftagunu = oku(cikti, "haftagunu.csv")
    urun = oku(cikti, "urun.csv")
    kampanya = oku(cikti, "kampanya.csv")

    ilk, son = aralik
    ps = []
    ps.append(
        f'<header><h1>Paket servis raporu</h1><span class="alt">{ilk:%d.%m.%Y} – {son:%d.%m.%Y} · {dosya_sayisi} fatura dosyası</span>'
        '<span class="bosluk"></span><a href="/yukle">Fatura yükle</a></header>'
    )
    if taninmayan:
        liste = ", ".join(taninmayan[:6]) + (f" ve {len(taninmayan) - 6} dosya daha" if len(taninmayan) > 6 else "")
        ps.append(
            f'<div class="not">{len(taninmayan)} dosya tanınmadı ve analize girmedi (yalnız Trendyol Go / GetirYemek faturaları okunuyor): {e(liste)}</div>'
        )

    ps.append('<div class="kpiler">')
    ps.append(kpi("Sipariş", tr(ozet.get("siparis")), f"{tr(ozet.get('kapida_siparis'))} kapıda ödemeli"))
    ps.append(kpi("Brüt satış", tl(ozet.get("brut")), f"Ort. sepet {tl(ozet.get('ort_sepet'))}"))
    ps.append(kpi("İndirim", tl(ozet.get("indirim")), f"Brütün {yuzde(ozet.get('indirim_orani'))} · indirimli sipariş {yuzde(ozet.get('indirimli_siparis_orani'))}"))
    ps.append(kpi("Komisyon", tl(ozet.get("komisyon")), f"Brütün {yuzde(ozet.get('komisyon_brut_orani'))}"))
    ps.append(kpi("Satıcı hakedişi", tl(ozet.get("hakedis")), f"Brütün {yuzde(ozet.get('hakedis_orani'))}"))
    ps.append(kpi("İade", tl(ozet.get("iade"), 2), ""))
    ps.append("</div>")

    if akis:
        renk = {"Brüt satış": "var(--c1)", "Satıcı hakedişi": "var(--iyi)"}
        ps.append('<section class="kart"><h2>Brütten hakedişe</h2>')
        ps.append(
            yatay_grafik(
                [r["adim"] for r in akis],
                [abs(sayi(r["tutar"])) for r in akis],
                [("-" if sayi(r["tutar"]) < 0 else "") + tl(abs(sayi(r["tutar"]))) for r in akis],
                [renk.get(r["adim"], "var(--c2)") for r in akis],
            )
        )
        ps.append("</section>")

    if platform:
        ps.append('<section class="kart"><h2>Platformlar</h2>')
        ps.append(
            tablo(
                ["Platform", "Sipariş", "Brüt", "İndirim %", "Hakediş", "Sipariş başı hakediş", "Ort. sepet"],
                [
                    (r["platform"], tr(r["siparis"]), tl(r["brut"]), yuzde(r["indirim_orani"]), tl(r["hakedis"]), tl(r["siparis_basi_hakedis"], 2), tl(r["ort_sepet"], 2))
                    for r in platform
                ],
                sag_kolonlar=range(1, 7),
            )
        )
        ps.append("</section>")

    ay_satirlar = aylik(cikti)
    if len(ay_satirlar) > 1:
        ps.append('<section class="kart"><h2>Aylık karşılaştırma</h2>')
        ps.append(tablo(["Ay", "Sipariş", "Brüt", "İndirim %", "Hakediş", "Ort. sepet"], ay_satirlar, sag_kolonlar=range(1, 6)))
        ps.append("</section>")

    if donem:
        ps.append('<section class="kart"><h2>Haftalık dönemler (günlük ortalama)</h2>')
        ps.append(
            yatay_grafik(
                [r["donem"] for r in donem],
                [sayi(r["gunluk_hakedis"]) for r in donem],
                [f"{tl(r['gunluk_hakedis'])} · {tr(r['gunluk_siparis'], 1)} sipariş" for r in donem],
                ["var(--iyi)"] * len(donem),
            )
        )
        ps.append(
            tablo(
                ["Dönem", "Gün", "Sipariş/gün", "İndirim %", "Hakediş/gün", "Ort. sepet"],
                [(r["donem"], tr(r["gun"]), tr(r["gunluk_siparis"], 1), yuzde(r["indirim_orani"], 2), tl(r["gunluk_hakedis"], 2), tl(r["ort_sepet"], 2)) for r in donem],
                sag_kolonlar=range(1, 6),
            )
        )
        ps.append("</section>")

    if gunluk:
        aralik_et = max(1, len(gunluk) // 12)
        ps.append('<section class="kart"><h2>Günlük sipariş sayısı</h2>')
        ps.append(dikey_grafik([r["gun"][5:].replace("-", ".") for r in gunluk][::1], [sayi(r["siparis"]) for r in gunluk], lambda d: tr(d), aralik_et))
        ps.append("</section>")

    if saat:
        ps.append('<section class="kart"><h2>Sipariş saati</h2>')
        ps.append(dikey_grafik([r["saat_etiket"][:2] for r in saat], [sayi(r["siparis"]) for r in saat], lambda d: tr(d), 1))
        ps.append("</section>")

    if haftagunu:
        ps.append('<section class="kart"><h2>Haftanın günleri (günlük ortalama sipariş)</h2>')
        kisa_gun = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]  # "Pazartesi" ile "Pazar" ilk 3 harfte çakışır
        ps.append(dikey_grafik([kisa_gun[int(sayi(r["dow"]))] for r in haftagunu], [sayi(r["gunluk_siparis"]) for r in haftagunu], lambda d: tr(d, 1), 1))
        ps.append('<p class="alt">Her gün türünün toplamı, o günden kaç tane bulunduğuna bölünür.</p></section>')

    if urun:
        ps.append('<section class="kart"><h2>Ürünler (ciroya göre)</h2>')
        ps.append(
            tablo(
                ["Ürün", "Kalem", "Ciro", "Pay", "Medyan fiyat"],
                [(r["urun"], tr(r["kalem"]), tl(r["ciro"]), yuzde(r["pay"]), tl(r["medyan_fiyat"], 2) if r["medyan_fiyat"] else "-") for r in urun],
                sag_kolonlar=range(1, 5),
            )
        )
        ps.append('<p class="alt">Kalem, sipariş satırı sayısıdır (adet değil).</p></section>')

    if kampanya:
        ps.append('<section class="kart"><h2>Kampanyalar</h2>')
        ps.append(
            tablo(
                ["Kampanya", "Sipariş", "Toplam indirim", "Ort. indirim", "İlk", "Son"],
                [(r["kampanya"] or "(adsız)", tr(r["siparis"]), tl(r["toplam_indirim"]), tl(r["ort_indirim"], 2), r["ilk"], r["son"]) for r in kampanya],
                sag_kolonlar=(1, 2, 3),
            )
        )
        ps.append("</section>")

    ps.append(f'<p class="alt">Üretim: {datetime.now():%d.%m.%Y %H:%M} (sunucu saati). Rapor yüklenen tüm faturalardan baştan hesaplanır.</p>')

    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Paket servis raporu</title>'
        f"<style>{CSS}</style></head><body><main>{''.join(ps)}</main></body></html>"
    )
