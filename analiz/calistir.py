"""
Paket servis analizini çalıştırır ve tek dosyalık HTML rapor yazar.

Kullanım: python3 calistir.py <girdi_klasoru> <cikti_klasoru> <rapor_html_yolu>

Girdi klasörü (alt klasörler ve zip arşivleri dahil) taranır; Trendyol Go ve Yemeksepeti raporları
dosya adından değil içeriğinden tanınır. Analizin başlangıç günü ANALIZ_BASLANGIC ortam değişkeniyle
(YYYY-AA-GG) değiştirilebilir.

Çıkış kodları: 0 başarılı, 3 analiz edilecek veri yok, 1 hata (son satır stderr'e yazılır).
"""
import json
import os
import sys
import warnings
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hesap  # noqa: E402
import okuma  # noqa: E402
import rapor  # noqa: E402

VARSAYILAN_BASLANGIC = date(2026, 9, 1)


def baslangic() -> date:
    s = os.environ.get("ANALIZ_BASLANGIC", "").strip()
    return date.fromisoformat(s) if s else VARSAYILAN_BASLANGIC


def main(girdi: str, cikti: str, rapor_yolu: str) -> int:
    warnings.filterwarnings("ignore", category=UserWarning)  # openpyxl'in stil uyarıları
    g = okuma.oku(girdi)
    if not any(t in g.tablolar for t in ("ty_online", "ty_kapida", "ys_siparis")):
        print("Analiz edilecek sipariş verisi yok (Trendyol komisyon fatura detayı ya da Yemeksepeti sipariş listesi gerekli).")
        return 3
    try:
        a = hesap.kur(g, baslangic())
    except SystemExit as e:
        if e.code == 3:
            print("Verinin kapsadığı tam bir fatura dönemi yok.")
            return 3
        raise
    if a.son < a.bas:
        print(f"Analiz başlangıcından ({a.bas:%d.%m.%Y}) sonra tamamlanmış dönem yok.")
        return 3
    html = rapor.uret(a, g)
    os.makedirs(cikti, exist_ok=True)
    ozet = {"bas": a.bas.isoformat(), "son": a.son.isoformat(), "magazalar": a.magazalar,
            "uyarilar": [{"magaza": u.magaza, "seviye": u.seviye, "metin": u.metin} for u in a.uyarilar],
            "dosyalar": [{"ad": k.ad, "tur": k.tur, "satir": k.satir, "durum": k.durum} for k in g.kayitlar]}
    with open(os.path.join(cikti, "ozet.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=1)
    with open(rapor_yolu, "w", encoding="utf-8") as f:
        f.write(html)
    okunan = sum(k.durum == "okundu" for k in g.kayitlar)
    hata = sum(u.seviye == "hata" for u in a.uyarilar)
    print(f"{a.bas:%d.%m.%Y}–{a.son:%d.%m.%Y}, {len(a.magazalar)} mağaza, {okunan} dosya okundu, {hata} kontrol hatası")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Kullanım: calistir.py <girdi_klasoru> <cikti_klasoru> <rapor_html_yolu>", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(*sys.argv[1:4]))
    except Exception as e:  # noqa: BLE001 - son satır arayüzde gösterilir
        print(f"Analiz hatası: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
