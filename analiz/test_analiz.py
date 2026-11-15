"""
Sentetik veriyle analiz testleri (gerçek fatura gerekmez; buradaki bütün tutarlar uydurmadır).
Çalıştırma (pandas ve openpyxl kurulu bir ortamda):  python3 -m unittest analiz/test_analiz.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calistir  # noqa: E402
import hesap  # noqa: E402
import okuma  # noqa: E402

MAGAZA = {"Mağaza No'su": 1, "Mağaza Adı": "Deneme Pide"}


def ty_satir(kayit, tip, siparis, zaman, urun, tutar, hak, sat, **ek):
    r = {"Kayıt No": kayit, "İşlem Tipi": tip, "Sipariş No": siparis, "Sipariş Tarihi": zaman, "İşlem Tarihi": zaman,
         "Satıcı": "Deneme", "Ürün Adı": urun, "Komisyon Oranı": 13.8, "Trendyol Hakediş": hak, "Satıcı Hakediş": sat,
         "Toplam Tutar": tutar, "Uygulama Adı": "Uber Eats TrendyolGo", **MAGAZA}
    r.update(ek)
    return r


def ys_siparis(no, zaman, odeme, ara, ind, kom, vergi, kazanc, nakit):
    return {"Restoran Adı": "Deneme Pide", "Sipariş No": no, "Şube No": "ab1", "Ödeme Türü": odeme, "Sipariş Durumu": "Alındı",
            "Siparişin Alındığı Zaman": zaman, "Ara Toplam": ara, "İndirim (İşletme tarafından karşılandı)": ind,
            "Kupon (İşletme tarafından karşılandı)": "0,00", "Komisyon": kom, "Vergi ücreti": vergi, "Reklam ücreti": "0,00",
            "Pazarlama ücretlerinin nedenleri": "", "Restoran para iadeleri": "0,00", "Faturalandırılabilir": "evet",
            "Tahmini Kazanç": kazanc, "İşletme tarafından tahsil edilmiş nakit tutar": nakit,
            "Yemeksepeti tarafından finanse edilen indirim": "0,00", "Yemeksepeti tarafından finanse edilen kupon": "0,00",
            "Sipariş ürünleri": "1 x Kaşarlı Pide"}


def ornek_veri(d, kazanc="1071.67"):
    on = pd.DataFrame([
        ty_satir(1, "Satış", "A1", "01.10.2026 12:30", "Kaşarlı Pide", 100.0, 13.80, 86.20),
        ty_satir(2, "İndirim", "A1", "01.10.2026 12:30", "Kaşarlı Pide - (300 TL’ye Varan İndirim - 20.00₺)", -20.0, -2.76, -17.24),
        ty_satir(3, "Satış", "B1", "05.10.2026 19:10", "Karışık Pide", 200.0, 27.60, 172.40),
    ])
    on.to_excel(os.path.join(d, "prod_2026_1_SaticiFatura_1_08.10.2026-01.00.xlsx"), index=False, sheet_name="Settlements")
    kp = pd.DataFrame([ty_satir(10, "Satış", "K1", "03.10.2026 13:00", "Kıymalı Pide", 300.0, 37.26, 232.74,
                                **{"Satıcı İndirim": -30.0, "Satici Kupon": 0, "TGO İndirim": 0, "TGO Kupon": 0, "Ödeme Tipi": "Kapıda Nakit"})])
    kp.to_excel(os.path.join(d, "PayWithOnDelivery_Komisyon_Fatura_Detayi_v1.xlsx"), index=False, sheet_name="Settlements")
    pd.DataFrame([
        {"Fatura No": "GCF1", "Tutar": -38.64, "Fatura Tipi": "Komisyon Faturası", "Kategori": "Komisyon Faturası",
         "Fatura Tarihi": "07.10.2026 03:00", "Statü": "Faturalandırıldı"},
        {"Fatura No": "GDF1", "Tutar": -37.26, "Fatura Tipi": "Kapıda Ödeme İşlemleri Komisyon Kesinti Faturası",
         "Kategori": "Kesinti Faturası", "Fatura Tarihi": "08.10.2026 02:00", "Statü": "Faturalandırıldı"},
        {"Fatura No": "GDF2", "Tutar": -30.00, "Fatura Tipi": "Reklam Bedeli", "Kategori": "Kesinti Faturası",
         "Fatura Tarihi": "05.10.2026 12:00", "Statü": "Faturalandırıldı"},
    ]).to_excel(os.path.join(d, "Faturalar_liste.xlsx"), index=False, sheet_name="Detay")
    # tek günlük reklam: kampanya adı başlangıç zamanı (05.10 12:00), fatura aynı dakikada kesilmiş
    pd.DataFrame([{"Şube No": 1, "Şube Adı": "Deneme Pide", "Gün": "2026-10-05", "Reklam Harcaması": 30.0, "Gösterim Sayısı": 100,
                   "Tıklanma Sayısı": 5, "Satış Adedi": 1, "Yeni Müşteri Sayısı": 1, "Ciro": 200.0, "Tıklanma Başına Maliyet": 6,
                   "Satış Başına Maliyet": 30, "Tıklanma Oranı": 5, "Reklam Getiri Katsayısı": 6.7, "Bölge Adı": "Bölge 1"}]
                 ).to_excel(os.path.join(d, "Reklam-05101200(deneme).xlsx"), index=False, sheet_name="Store Reports")
    pd.DataFrame([{"Müşteri Mesajı": "<script>alert(1)</script> soğuktu", "Restoran Cevabı": None, "Sipariş Tarihi": "05.10.2026 19:10",
                   "Değerlendirme Tarihi": "06.10.2026 10:00", "Lezzet Puanı": "2,00", "Servis Puanı": "3,00", "Teslimat Puanı": "1,00",
                   "Ortalama Puan": "2,00", "Beğenilen Ürünler": None, "Platform": "Trendyol Go"}]
                 ).to_excel(os.path.join(d, "x_1_Değerlendirmeler_07.10.2026.xlsx"), index=False)
    # Yemeksepeti: sipariş listesi Türkçe sayı biçiminde, fatura özeti noktalı ondalıkla gelir
    pd.DataFrame([
        ys_siparis("ab1-1", "2026-10-02 12:00:00", "Online", "1.000,00", "150,00", "102,00", "28,13", "719,87", "0,00"),
        ys_siparis("ab1-2", "2026-10-04 20:00:00", "Kapıda Ödeme", "500,00", "75,00", "51,00", "10,20", "363,80", "425,00"),
    ]).to_csv(os.path.join(d, "ys_siparis.csv"), index=False)
    pd.DataFrame([{"Fatura No": "200", "Başlangıç Tarihi": "2026-10-01", "Bitiş Tarihi": "2026-10-07", "Toplam Kazanç": kazanc,
                   "Sipariş Sayısı": "2", "Tahsil Edilen Nakit Tutarı": "-425.00", "Toplam Ödeme": "646.67", "Brüt Satışlar": "1500.00",
                   "Komisyon Bedeli": "-153.00", "Toplam Ek Ücretler": "-10.00", "Ek Ücret Nedenleri": "Öne Çıkan Reklam Gelirleri (CPC)",
                   "Ek Ücretler / Kesintiler": "-10.00", "İşletme Tarafından Karşılanan İndirimler": "-225.00",
                   "İşletme Tarafından Karşılanan Kuponlar": "0.00", "Pazarlama Ücretleri": "0.00"}]
                 ).to_csv(os.path.join(d, "ys_fatura.csv"), index=False)
    pd.DataFrame([{"Tarih": t, "Restoran No": "ab1", "Şube Adı": "Deneme Pide", "Başarılı siparişler": "1", "Görüntülenme Sayısı": "100",
                   "Menü Görüntüleme Sayısı": "20", "Sepete eklenen ürünler": "5", "Sipariş Veren Müşteri Sayısı": "1"}
                  for t in ("2026-10-01", "2026-10-07")]).to_csv(os.path.join(d, "ys_performans.csv"), index=False)


class Donemler(unittest.TestCase):
    def test_fatura_donemleri(self):
        self.assertEqual(hesap.donemler(date(2026, 9, 1), date(2026, 10, 10))[3:6],
                         [(date(2026, 9, 22), date(2026, 9, 28)), (date(2026, 9, 29), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 7))])
        self.assertEqual(hesap.donem_bit(date(2027, 2, 22)), date(2027, 2, 28))
        self.assertEqual(hesap.donem_bit(date(2028, 2, 29)), date(2028, 2, 29))
        self.assertEqual(hesap.etiket(date(2026, 10, 29), date(2026, 10, 31)), "29–31 Eki")


class Donusturuculer(unittest.TestCase):
    def test_sayi(self):
        self.assertEqual(okuma.sayi("1.364,50"), 1364.5)
        self.assertEqual(okuma.sayi("169799.75"), 169799.75)
        self.assertEqual(okuma.sayi("5,00"), 5.0)
        self.assertEqual(okuma.sayi(""), 0.0)
        self.assertEqual(okuma.sayi(12), 12.0)

    def test_kampanya_adi(self):
        self.assertEqual(hesap.ty_kampanya_adi("Pide - (300 TL’ye Varan İndirim - 111.79₺)"), "300 TL'ye Varan İndirim")
        self.assertEqual(hesap.ty_kampanya_adi("Tabak (150 gr) - (Plus Yemek Kuponu (Mobil Uygulamaya Özel) - 96.47₺)"),
                         "Plus Yemek Kuponu (Mobil Uygulamaya Özel)")
        self.assertEqual(hesap.ty_kampanya_adi("Ayran"), "(adı yok)")

    def test_reklam_kodu(self):
        self.assertEqual(hesap.reklam_kodu_zamani("12091428", date(2026, 9, 12)), datetime(2026, 9, 12, 14, 28))
        self.assertEqual(hesap.reklam_kodu_zamani("30121000P", date(2027, 1, 1)), datetime(2026, 12, 30, 10, 0))


class UctanUca(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.girdi = os.path.join(self.d, "girdi")
        os.makedirs(self.girdi)
        os.environ["ANALIZ_BASLANGIC"] = "2026-10-01"

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("ANALIZ_BASLANGIC", None)

    def calistir(self):
        rapor_yolu = os.path.join(self.d, "rapor.html")
        kod = calistir.main(self.girdi, os.path.join(self.d, "c"), rapor_yolu)
        with open(os.path.join(self.d, "c", "ozet.json"), encoding="utf-8") as f:
            ozet = json.load(f)
        with open(rapor_yolu, encoding="utf-8") as f:
            return kod, ozet, f.read()

    def test_toplamlar_ve_kontroller(self):
        ornek_veri(self.girdi)
        # birebir kopya bir kez sayılmalı
        shutil.copy(os.path.join(self.girdi, "prod_2026_1_SaticiFatura_1_08.10.2026-01.00.xlsx"),
                    os.path.join(self.girdi, "prod_2026_1_SaticiFatura_1_08.10.2026-01.00 (1).xlsx"))
        kod, ozet, html = self.calistir()
        self.assertEqual(kod, 0)
        self.assertEqual((ozet["bas"], ozet["son"]), ("2026-10-01", "2026-10-07"))
        self.assertEqual(ozet["magazalar"], ["Deneme Pide"])
        self.assertEqual([u for u in ozet["uyarilar"] if u["seviye"] == "hata"], [])
        self.assertTrue(any(k["durum"].startswith("kopya") for k in ozet["dosyalar"]))

        a = hesap.kur(okuma.oku(self.girdi), date(2026, 10, 1))
        t = hesap.trend(a, "Deneme Pide").set_index("platform")
        self.assertEqual(int(t.loc[hesap.TY, "siparis"]), 3)
        self.assertAlmostEqual(t.loc[hesap.TY, "brut"], 600.0)
        self.assertAlmostEqual(t.loc[hesap.TY, "kampanya"], 50.0)
        self.assertAlmostEqual(t.loc[hesap.TY, "komisyon"], 75.90)
        self.assertAlmostEqual(t.loc[hesap.TY, "reklam"], 30.0)
        self.assertAlmostEqual(t.loc[hesap.TY, "kalan"], 444.10)  # satıcı hakedişi 474,10 − reklam 30
        self.assertEqual(int(t.loc[hesap.YS, "siparis"]), 2)
        self.assertAlmostEqual(t.loc[hesap.YS, "kampanya"], 225.0)
        self.assertAlmostEqual(t.loc[hesap.YS, "komisyon"], 183.60)
        self.assertAlmostEqual(t.loc[hesap.YS, "reklam"], 12.0)
        self.assertAlmostEqual(t.loc[hesap.YS, "kalan"], 1071.67)
        self.assertEqual(set(hesap.ty_komisyon_kontrol(a, "Deneme Pide", "ty_online")["durum"]), {"Tuttu"})
        self.assertEqual(set(hesap.ty_komisyon_kontrol(a, "Deneme Pide", "ty_kapida")["durum"]), {"Tuttu"})
        self.assertEqual(set(hesap.ys_fatura_kontrol(a, "Deneme Pide")["durum"]), {"Tuttu"})
        k = hesap.kampanyalar(a, "Deneme Pide").set_index("ad")
        self.assertIn("300 TL'ye Varan İndirim", k.index)
        self.assertIn("Kampanya 1 (%15 indirim)", k.index)

        # reklam: fatura kampanyaya bağlanır, gün "tekil" sayılır; tek haftalık veride baz yok, sonuç güvenilir değil
        rk = a.ty_reklam_kampanya.set_index("kampanya")
        self.assertEqual(rk.loc["05101200", "durum"], "Tutuyor")
        self.assertEqual(hesap.gunluk(a, "Deneme Pide").loc[date(2026, 10, 5), "tur"], "tekil")
        tek = hesap.tekil_reklam(a, "Deneme Pide")
        self.assertEqual(len(tek), 1)
        self.assertFalse(bool(tek.iloc[0]["guvenilir"]))
        # ay ve ay ayrıntısı
        ay = hesap.aylar(a, "Deneme Pide")
        self.assertEqual(len(ay), 1)
        self.assertFalse(bool(ay.iloc[0]["tam"]))  # yalnız 1–7 Ekim
        ayr = hesap.ay_ayrintisi(a, "Deneme Pide", date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual(int(ayr["saat"].sum().sum()), 5)
        self.assertAlmostEqual(ayr["urun"][ayr["urun"]["platform"] == hesap.TY]["ciro"].sum(), 600.0)

        self.assertIn("Ekim 2026", html)
        self.assertIn("Günlük sipariş ve reklam günleri", html)
        self.assertTrue(html.lower().startswith("<!doctype html"))
        self.assertIn("Deneme Pide", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)

    def test_fatura_tutmazsa_hata(self):
        ornek_veri(self.girdi, kazanc="1076.67")
        kod, ozet, _ = self.calistir()
        self.assertEqual(kod, 0)
        self.assertTrue(any(u["seviye"] == "hata" and "kazanç" in u["metin"] for u in ozet["uyarilar"]))

    def test_veri_yoksa_3(self):
        self.assertEqual(calistir.main(self.girdi, os.path.join(self.d, "c"), os.path.join(self.d, "r.html")), 3)


if __name__ == "__main__":
    unittest.main()
