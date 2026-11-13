"""
Sunucu için analiz çalıştırıcı.

Kullanım: python3 calistir.py <fatura_klasoru> <cikti_klasoru> <rapor_html_yolu>

fatura_analiz.py (referans uygulama) DEĞİŞTİRİLMEDEN kullanılır; bu dosya yalnızca onu çağırır:
 - dönemleri sabit yazmak yerine verinin kapsadığı tarih aralığından haftalık (pazartesi-pazar) üretir
 - çıkan CSV'lerden rapor.py ile tek dosyalık HTML rapor yazar

Çıkış kodları: 0 başarılı, 3 analiz edilecek fatura yok, 1 hata (son satır stderr'e yazılır).
"""
import glob
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fatura_analiz as fa  # noqa: E402
import rapor  # noqa: E402

AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
ONLINE_DESEN = "*SaticiFatura*.xlsx"
KAPIDA_DESEN = "*PayWithOnDelivery*.xlsx"


def etiket(bas: date, bit: date) -> str:
    if bas == bit:
        return f"{bas.day} {AY[bas.month - 1]}"
    if bas.month == bit.month:
        return f"{bas.day}–{bit.day} {AY[bas.month - 1]}"
    return f"{bas.day} {AY[bas.month - 1]} – {bit.day} {AY[bit.month - 1]}"


def haftalar(ilk: date, son: date):
    """Verinin ilk ve son gününe kırpılmış pazartesi-pazar haftaları: (etiket, 'YYYY-MM-DD', 'YYYY-MM-DD')."""
    satirlar = []
    d = ilk
    while d <= son:
        bit = min(d + timedelta(days=6 - d.weekday()), son)
        satirlar.append((etiket(d, bit), d.isoformat(), bit.isoformat()))
        d = bit + timedelta(days=1)
    return satirlar


def main(faturalar: str, cikti: str, rapor_yolu: str) -> int:
    taninan = sorted(glob.glob(os.path.join(faturalar, ONLINE_DESEN)) + glob.glob(os.path.join(faturalar, KAPIDA_DESEN)))
    if not taninan:
        print("Analiz edilecek Trendyol Go / GetirYemek faturası yok (dosya adında SaticiFatura veya PayWithOnDelivery geçmeli).")
        return 3

    online, kapida = fa.yukle(faturalar)
    siparisler = fa.siparis_tablosu(online, kapida)
    ilk, son = siparisler.t.min().date(), siparisler.t.max().date()
    fa.analiz(faturalar, cikti, haftalar(ilk, son))

    tum = set(glob.glob(os.path.join(faturalar, "*.xlsx")))
    taninmayan = sorted(os.path.basename(f) for f in tum - set(taninan))
    html = rapor.uret(cikti, dosya_sayisi=len(taninan), taninmayan=taninmayan, aralik=(ilk, son))
    with open(rapor_yolu, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{len(siparisler)} sipariş, {ilk:%d.%m.%Y}–{son:%d.%m.%Y}, {len(taninan)} fatura dosyası")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Kullanım: calistir.py <fatura_klasoru> <cikti_klasoru> <rapor_html_yolu>", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(*sys.argv[1:4]))
    except Exception as e:  # noqa: BLE001 - son satır arayüzde gösterilir
        print(f"Analiz hatası: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
