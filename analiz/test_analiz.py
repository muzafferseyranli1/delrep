"""
Sentetik fatura verisiyle uçtan uca kontrol (gerçek fatura gerekmez).
Çalıştırma (pandas ve openpyxl kurulu bir ortamda):  python3 -m unittest analiz/test_analiz.py
Dikkat: bu yalnız hattın çalıştığını ve toplamların tutarlı çıktığını doğrular; gerçek Ekim kontrol değerleri
(DEVIR_NOTU.md) gerçek faturalarla ayrıca karşılaştırılmalıdır.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calistir  # noqa: E402

KOLONLAR = ["Kayıt No", "İşlem Tipi", "Sipariş No", "Sipariş Tarihi", "Ürün Adı", "Komisyon Oranı",
            "Trendyol Hakediş", "Satıcı Hakediş", "Toplam Tutar", "Uygulama Adı"]


def satir(kayit, tip, siparis, tarih, urun, tutar, uygulama):
    net = tutar
    return [kayit, tip, siparis, tarih, urun, "13.8", f"{net * 0.138:.2f}", f"{net * 0.862:.2f}", f"{tutar:.2f}", uygulama]


class AnalizHatti(unittest.TestCase):
    def test_haftalar_pazartesi_pazar_ve_kirpma(self):
        h = calistir.haftalar(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual([x[0] for x in h], ["1–4 Eki", "5–11 Eki", "12–18 Eki", "19–25 Eki", "26–31 Eki"])

    def test_uctan_uca(self):
        with tempfile.TemporaryDirectory() as d:
            fat, cikti = os.path.join(d, "f"), os.path.join(d, "c")
            os.makedirs(fat)
            rows = [
                satir("1", "Satış", "A1", "01.10.2026 12:30", "Kaşarlı Pide", 100.0, "Uber Eats TrendyolGo"),
                satir("2", "İndirim", "A1", "01.10.2026 12:30", "Kaşarlı Pide - (300 TL'ye Varan İndirim - 20.00₺)", -20.0, "Uber Eats TrendyolGo"),
                satir("3", "Satış", "B1", "08.10.2026 19:10", "Karışık Pide", 200.0, "GetirYemek by Uber Eats"),
            ]
            pd.DataFrame(rows, columns=KOLONLAR).to_excel(os.path.join(fat, "prod_2026_1_SaticiFatura_1_08.10.2026-10.00.xlsx"), index=False)
            rapor_yolu = os.path.join(d, "rapor.html")
            self.assertEqual(calistir.main(fat, cikti, rapor_yolu), 0)
            ozet = pd.read_csv(os.path.join(cikti, "ozet.csv")).iloc[0]
            self.assertEqual(int(ozet.siparis), 2)
            self.assertAlmostEqual(ozet.brut, 300.0)
            self.assertAlmostEqual(ozet.indirim, 20.0)
            self.assertAlmostEqual(ozet.net, 280.0)
            with open(rapor_yolu, encoding="utf-8") as f:
                html = f.read()
            self.assertTrue(html.lower().startswith("<!doctype html"))
            self.assertIn("Paket servis raporu", html)
            self.assertNotIn("<script", html.lower())

    def test_fatura_yoksa_3(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(calistir.main(d, os.path.join(d, "c"), os.path.join(d, "r.html")), 3)


if __name__ == "__main__":
    unittest.main()
