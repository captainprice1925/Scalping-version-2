# -*- coding: utf-8 -*-
"""Portföy seviyesinde kronolojik backtest motoru.

`paper_trade.py` kurallarının 1h barlarla birebir aynası:

- Giriş: 1h bar kapanışı + giriş kayması + taker komisyonu
- Boyutlandırma: %1 işlem riski, %2 toplam açık risk, marjin tavanları
- Seviyeler: SL 1.5 ATR, TP1 1.2 ATR, TP2 1.89 ATR, TP3 2.7 ATR
- Çıkış: aynı barda SL önce (kötümser), TP1 %40 → SL girişe, TP2 %30 →
  SL TP1'e, TP3 kalanı; 24 saatte kapanmayan ZAMAN ile çıkar
- Cooldown: STOP 240 dk, BE 45 dk
- Günlük %3 kayıp limiti, %20 max drawdown (efektif bakiye, mark-to-market)
- Fonlama yok (işlem başına etkisi ~$0.01, ihmal edildi)
- Spread filtresi yok (1h barında ölçülemez)

Bu modül canlı bot tarafından import edilmez.
"""
import uuid

import pandas as pd

from faz1_engine import full_analysis
from backtest.simule import (
    cikis_fill,
    filtreli_skor,
    giris_fill,
    seviyeler,
    varsayilan_cfg,
)
from backtest.veri import dort_saatlik


def hazirla(df_1h, df_4h=None):
    """1h verisine göstergeleri ekler; 4h seriyi ve 4h eşlemesini kurar."""
    df1 = full_analysis(df_1h.copy().sort_values("time").reset_index(drop=True))
    if df_4h is None:
        df_4h = dort_saatlik(df1[["time", "open", "high", "low", "close", "volume"]])
    df4 = full_analysis(df_4h.copy().sort_values("time").reset_index(drop=True))

    # 1h barı t'de kapanır (t + 1h). O anda en son KAPANMIŞ 4h barı,
    # kapanışı t + 1h'den büyük olmayan son bardır.
    kapanis4 = (df4["time"] + pd.Timedelta(hours=4)).values
    kapanis1 = (df1["time"] + pd.Timedelta(hours=1)).values
    idx4 = kapanis4.searchsorted(kapanis1, side="right") - 1
    return {"1h": df1, "4h": df4, "idx4": idx4}


def rejim_haritasi(s, btc_df_1h=None):
    """1h zaman damgası -> BTC 4h rejimi (close > ema200)."""
    if btc_df_1h is None:
        return {}
    b = hazirla(btc_df_1h)
    harita = {}
    for i, t in enumerate(b["1h"]["time"]):
        j = b["idx4"][i]
        if j < 0 or j + 1 < 210:
            continue
        r4 = b["4h"].iloc[j]
        if pd.isna(r4["ema_200"]):
            continue
        harita[t] = bool(r4["close"] > r4["ema_200"])
    return harita


def sinyal_uret(s, i, cfg, btc_yukari):
    """Canlı `calculate_score_fatih` + BTC rejim filtresinin aynası."""
    df1, df4 = s["1h"], s["4h"]
    if i + 1 < 50:
        return None
    j = s["idx4"][i]
    if j < 0 or j + 1 < 210:
        return None

    r1 = df1.iloc[i]
    r4 = df4.iloc[j]
    if (
        pd.isna(r1["ema_21"])
        or pd.isna(r1["rsi"])
        or pd.isna(r1["atr_pct"])
        or pd.isna(r1["volume_ratio"])
        or pd.isna(r4["ema_200"])
        or pd.isna(r4["rsi"])
    ):
        return None

    close1 = float(r1["close"])
    ema_dist = abs(close1 - float(r1["ema_21"])) / close1 * 100
    trend_long = bool(r4["close"] > r4["ema_200"])
    skor, yon = filtreli_skor(
        trend_long,
        ema_dist,
        float(r1["volume_ratio"]),
        float(r1["rsi"]),
        float(r1["atr_pct"]),
        cfg,
    )
    if not yon:
        return None

    if cfg["BTC_REGIME_FILTRE"] and btc_yukari is not None:
        if (yon == "LONG") != btc_yukari:
            return None

    gosterge = {
        "rsi_1h": float(r1["rsi"]),
        "ema_dist": ema_dist,
        "vol_ratio": float(r1["volume_ratio"]),
        "atr_pct": float(r1["atr_pct"]),
        "macd_hist": float(r1.get("macd_hist", 0.0) or 0.0),
        "rsi_4h": float(r4["rsi"]),
        "ema200_dist": (float(r4["close"]) - float(r4["ema_200"]))
        / float(r4["close"])
        * 100,
        "btc_yukari": btc_yukari,
    }
    return yon, skor, gosterge


def boyutlandir(direction, entry, sl, efektif, mevcut_risk, kullanilan_marjin, cfg):
    """`PaperTrade._pozisyon_boyutlandir` ile aynı hesap (parite testi var)."""
    giris = giris_fill(entry, direction, cfg)
    cikis = cikis_fill(sl, direction, cfg)
    fiyat_riski = abs(cikis - giris) / giris
    maliyet_orani = cfg["GIRIS_KOMISYON_ORANI"] + cfg["CIKIS_KOMISYON_ORANI"]
    birim_risk = fiyat_riski + maliyet_orani
    if birim_risk <= 0:
        return None

    toplam_risk_limiti = efektif * cfg["MAX_TOPLAM_RISK_YUZDE"]
    tek_islem_notional = efektif * cfg["RISK_YUZDE_ISLEM"] / birim_risk
    toplam_risk_notional = (toplam_risk_limiti - mevcut_risk) / (
        birim_risk + birim_risk * cfg["MAX_TOPLAM_RISK_YUZDE"]
    )
    if toplam_risk_notional <= 0:
        return None

    hesaplanan_notional = min(tek_islem_notional, toplam_risk_notional)
    hesaplanan_marjin = hesaplanan_notional / cfg["KALDIRAC"]
    musait_toplam_marjin = efektif * cfg["MAX_TOPLAM_MARJIN_YUZDE"] - kullanilan_marjin
    marjin_limiti = min(
        max(cfg["MAX_ISLEM_MARJINI"], efektif * cfg["MAX_ISLEM_MARJINI_ORAN"]),
        efektif * cfg["MAX_TOPLAM_MARJIN_YUZDE"],
        musait_toplam_marjin,
    )
    marjin = min(hesaplanan_marjin, marjin_limiti)
    if marjin < cfg["MIN_ISLEM_MARJINI"]:
        return None

    notional = marjin * cfg["KALDIRAC"]
    return {
        "marjin": marjin,
        "notional": notional,
        "giris_fiyati": giris,
        "giris_komisyonu": notional * cfg["GIRIS_KOMISYON_ORANI"],
        "tahmini_stop_riski": notional * birim_risk,
    }


class Motor:
    def __init__(self, veriler, cfg=None):
        """veriler: {sembol: 1h DataFrame(time/open/high/low/close/volume)}"""
        self.cfg = cfg or varsayilan_cfg()
        self.s = {sembol: hazirla(df) for sembol, df in veriler.items()}
        self.btc = rejim_haritasi(self.s["BTCUSDT"], veriler["BTCUSDT"]) if "BTCUSDT" in self.s else {}

        self.bakiye = self.cfg["BUTCE_SANAL"]
        self.peak = self.cfg["BUTCE_SANAL"]
        self.pozisyonlar = []
        self.kayitlar = []
        self.equity = []
        self.cooldown = {}
        self.gun = None
        self.gun_baslangic = self.cfg["BUTCE_SANAL"]
        self.gunluk_pnl = 0.0

    # ---------------------------------------------------------------- değerler
    def _kalan_oran(self, poz):
        return poz["kalan_yuzde"] / 100

    def _kalan_marjin(self, poz):
        return poz["miktar"] * self._kalan_oran(poz)

    def _kalan_notional(self, poz):
        return poz["notional"] * self._kalan_oran(poz)

    def _brut_pnl(self, poz, ham_cikis, yuzde=None):
        oran = self._kalan_oran(poz) if yuzde is None else yuzde / 100
        notional = poz["notional"] * oran
        cikis = cikis_fill(ham_cikis, poz["direction"], self.cfg)
        if poz["direction"] == "LONG":
            return (cikis - poz["giris_fiyat"]) / poz["giris_fiyat"] * notional
        return (poz["giris_fiyat"] - cikis) / poz["giris_fiyat"] * notional

    def _cikis_komisyonu(self, poz):
        return self._kalan_notional(poz) * self.cfg["CIKIS_KOMISYON_ORANI"]

    def _stop_riski(self, poz):
        risk = max(0.0, -self._brut_pnl(poz, poz["sl"])) + self._cikis_komisyonu(poz)
        risk += poz["giris_komisyonu"] * self._kalan_oran(poz)
        return risk

    def _acik_deger(self, poz):
        return (
            self._kalan_marjin(poz)
            + self._brut_pnl(poz, poz["son_fiyat"])
            - self._cikis_komisyonu(poz)
        )

    def _efektif(self):
        return self.bakiye + sum(self._acik_deger(p) for p in self.pozisyonlar)

    def _kullanilan_marjin(self):
        return sum(self._kalan_marjin(p) for p in self.pozisyonlar)

    def _acik_risk(self):
        return sum(self._stop_riski(p) for p in self.pozisyonlar)

    # ---------------------------------------------------------------- kapanış
    def _kapat(self, poz, ham_cikis, yuzde, sebep, zaman):
        if yuzde <= 0 or poz not in self.pozisyonlar:
            return
        yuzde = min(yuzde, poz["kalan_yuzde"])
        marjin = poz["miktar"] * (yuzde / 100)
        notional = poz["notional"] * (yuzde / 100)
        cikis = cikis_fill(ham_cikis, poz["direction"], self.cfg)
        brut = self._brut_pnl(poz, ham_cikis, yuzde=yuzde)
        cikis_komisyonu = notional * self.cfg["CIKIS_KOMISYON_ORANI"]
        giris_payi = poz["giris_komisyonu"] * (yuzde / 100)
        net = brut - cikis_komisyonu - giris_payi

        self.bakiye += marjin + brut - cikis_komisyonu
        self.gunluk_pnl += net
        self.kayitlar.append(
            {
                "poz_id": poz["id"],
                "symbol": poz["symbol"],
                "direction": poz["direction"],
                "entry": poz["giris_fiyat"],
                "exit": cikis,
                "yuzde": yuzde,
                "sebep": sebep,
                "skor": poz["skor"],
                "atr_pct": poz["gosterge_an"]["atr_pct"],
                "brut_pnl": brut,
                "komisyon": giris_payi + cikis_komisyonu,
                "pnl": net,
                "giris_zamani": poz["acilis"],
                "zaman": zaman,
                "gosterge_an": poz["gosterge_an"],
            }
        )

        tam = poz["kalan_yuzde"] - yuzde <= 0
        if tam:
            self.pozisyonlar.remove(poz)
            if sebep == "STOP":
                self.cooldown[poz["symbol"]] = zaman + pd.Timedelta(
                    minutes=self.cfg["COOLDOWN_DAKIKA"]
                )
            elif sebep == "BE":
                self.cooldown[poz["symbol"]] = zaman + pd.Timedelta(
                    minutes=self.cfg["COOLDOWN_BE_DAKIKA"]
                )
        else:
            poz["kalan_yuzde"] -= yuzde

    def _bar_isle(self, poz, o, h, l, c, t):
        """Tek 1h barı; canlı `pozisyon_guncelle` sırası (SL önce)."""
        cfg = self.cfg
        if (t - poz["acilis"]).total_seconds() > cfg["ZAMAN_EXIT_SAAT"] * 3600:
            self._kapat(poz, c, poz["kalan_yuzde"], "ZAMAN", t)
            return
        if poz["direction"] == "LONG":
            if l <= poz["sl"]:
                self._kapat(
                    poz,
                    min(o, poz["sl"]),
                    poz["kalan_yuzde"],
                    "BE" if poz["tp1_tetiklendi"] else "STOP",
                    t,
                )
                return
            if h >= poz["tp1"]:
                self._tp1(poz, t)
            if poz not in self.pozisyonlar:
                return
            if h >= poz["tp2"]:
                self._tp2(poz, t)
            if poz not in self.pozisyonlar:
                return
            if h >= poz["tp3"]:
                self._kapat(poz, poz["tp3"], poz["kalan_yuzde"], "TP3", t)
        else:
            if h >= poz["sl"]:
                self._kapat(
                    poz,
                    max(o, poz["sl"]),
                    poz["kalan_yuzde"],
                    "BE" if poz["tp1_tetiklendi"] else "STOP",
                    t,
                )
                return
            if l <= poz["tp1"]:
                self._tp1(poz, t)
            if poz not in self.pozisyonlar:
                return
            if l <= poz["tp2"]:
                self._tp2(poz, t)
            if poz not in self.pozisyonlar:
                return
            if l <= poz["tp3"]:
                self._kapat(poz, poz["tp3"], poz["kalan_yuzde"], "TP3", t)

    def _tp1(self, poz, t):
        if poz["tp1_tetiklendi"]:
            return
        self._kapat(poz, poz["tp1"], self.cfg["TP1_YUZDE"], "TP1", t)
        if poz in self.pozisyonlar:
            poz["sl"] = poz["giris_fiyat"]
            poz["tp1_tetiklendi"] = True

    def _tp2(self, poz, t):
        if poz["tp2_tetiklendi"]:
            return
        self._tp1(poz, t)
        if poz not in self.pozisyonlar:
            return
        self._kapat(poz, poz["tp2"], self.cfg["TP2_YUZDE"], "TP2", t)
        if poz in self.pozisyonlar:
            poz["sl"] = poz["tp1"]
            poz["tp2_tetiklendi"] = True

    # ---------------------------------------------------------------- giriş
    def _gunluk_kontrol(self, t):
        if self.gun != t.date():
            self.gun = t.date()
            self.gunluk_pnl = 0.0
            self.gun_baslangic = self._efektif()
        limit = self.gun_baslangic * self.cfg["GUNLUK_KAYIP_LIMITI"]
        return max(0.0, -self.gunluk_pnl) >= limit

    def _dd_aktif(self):
        return self._efektif() < self.peak * (1 - self.cfg["MAX_DRAWDOWN"])

    def _giris_dene(self, sembol, i, yon, skor, gosterge, t):
        cfg = self.cfg
        if self._gunluk_kontrol(t) or self._dd_aktif():
            return False
        bitis = self.cooldown.get(sembol)
        if bitis is not None and t < bitis:
            return False
        if any(p["symbol"] == sembol for p in self.pozisyonlar):
            return False
        if len(self.pozisyonlar) >= cfg["MAX_POZISYON"]:
            return False
        if (
            sum(1 for p in self.pozisyonlar if p["direction"] == yon)
            >= cfg["MAX_AYNI_YON"]
        ):
            return False

        r = self.s[sembol]["1h"].iloc[i]
        entry = float(r["close"])
        atr = float(r["atr"])
        if atr <= 0 or entry <= 0:
            return False
        lv = seviyeler(entry, yon, atr, cfg)

        efektif = self._efektif()
        boyut = boyutlandir(
            yon,
            entry,
            lv["sl"],
            efektif,
            self._acik_risk(),
            self._kullanilan_marjin(),
            cfg,
        )
        if boyut is None:
            return False

        likidasyon = boyut["giris_fiyati"] * (
            (1 - 1 / cfg["KALDIRAC"])
            if yon == "LONG"
            else (1 + 1 / cfg["KALDIRAC"])
        )
        tampon = cfg.get("LIKIDASYON_TAMPON_YUZDE", 0.005)
        if yon == "LONG":
            guvenli = lv["sl"] > likidasyon * (1 + tampon)
        else:
            guvenli = lv["sl"] < likidasyon * (1 - tampon)
        if not guvenli:
            return False
        if self.bakiye < boyut["marjin"] + boyut["giris_komisyonu"]:
            return False

        poz = {
            "id": uuid.uuid4().hex,
            "symbol": sembol,
            "direction": yon,
            "acilis": t,
            "entry_ham": entry,
            "giris_fiyat": boyut["giris_fiyati"],
            "son_fiyat": entry,
            "atr": atr,
            "sl": lv["sl"],
            "tp1": lv["tp1"],
            "tp2": lv["tp2"],
            "tp3": lv["tp3"],
            "skor": skor,
            "miktar": boyut["marjin"],
            "notional": boyut["notional"],
            "giris_komisyonu": boyut["giris_komisyonu"],
            "kalan_yuzde": 100,
            "tp1_tetiklendi": False,
            "tp2_tetiklendi": False,
            "gosterge_an": gosterge,
        }
        self.pozisyonlar.append(poz)
        self.bakiye -= boyut["marjin"] + boyut["giris_komisyonu"]
        return True

    # ---------------------------------------------------------------- ana döngü
    def calistir(self, baslangic=None, bitis=None, ilerleme=False):
        zamanlar = sorted(set().union(*(set(s["1h"]["time"]) for s in self.s.values())))
        indeksler = {
            sembol: dict(zip(s["1h"]["time"], range(len(s["1h"]))))
            for sembol, s in self.s.items()
        }

        for adim, t in enumerate(zamanlar):
            if baslangic is not None and t < baslangic:
                continue
            if ilerleme and adim % 1000 == 0:
                print(f"  ⏳ {t} — bakiye ${self.bakiye:.2f}")

            kapanan = []
            for sembol, s in self.s.items():
                i = indeksler[sembol].get(t)
                if i is None:
                    continue
                r = s["1h"].iloc[i]
                o, h, l, c = (
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                )
                for poz in self.pozisyonlar[:]:
                    if poz["symbol"] != sembol:
                        continue
                    self._bar_isle(poz, o, h, l, c, t)
                    if poz in self.pozisyonlar:
                        poz["son_fiyat"] = c
                    else:
                        kapanan.append(sembol)

            self.peak = max(self.peak, self._efektif())

            # Girişler: aynı barın kapanışından, çıkışlardan sonra.
            if bitis is None or t <= bitis:
                for sembol, s in self.s.items():
                    i = indeksler[sembol].get(t)
                    if i is None:
                        continue
                    btc_yukari = self.btc.get(t)
                    sinyal = sinyal_uret(s, i, self.cfg, btc_yukari)
                    if sinyal is None:
                        continue
                    yon, skor, gosterge = sinyal
                    self._giris_dene(sembol, i, yon, skor, gosterge, t)

            self.equity.append(
                {
                    "zaman": t,
                    "bakiye": self.bakiye,
                    "efektif": self._efektif(),
                    "peak": self.peak,
                    "acik": len(self.pozisyonlar),
                }
            )

        # Veri bitti: açık pozisyonları son kapanıştan kapat.
        if self.pozisyonlar:
            son = zamanlar[-1]
            for poz in self.pozisyonlar[:]:
                s = self.s[poz["symbol"]]
                i = indeksler[poz["symbol"]][son]
                self._kapat(
                    poz, float(s["1h"]["close"].iat[i]), poz["kalan_yuzde"], "VERI_SONU", son
                )
        return self.sonuc()

    def sonuc(self):
        return ozet(self.kayitlar, self.equity)


def ozet(kayitlar, equity):
    """İşlem kayıtlarından ve equity eğrisinden özet metrikler."""
    if not kayitlar:
        return {
            "islem": 0,
            "pnl": 0.0,
            "wr": 0.0,
            "ev": 0.0,
            "max_dd": 0.0,
            "komisyon": 0.0,
            "son_bakiye": None,
        }

    gruplar = {}
    for k in kayitlar:
        gruplar.setdefault(k["poz_id"], []).append(k)
    islemler = list(gruplar.values())
    pnl = [sum(k["pnl"] for k in kayit) for kayit in islemler]
    kazanan = [p for p in pnl if p > 0]
    kaybeden = [p for p in pnl if p <= 0]

    max_dd = 0.0
    tepe = None
    for e in equity:
        tepe = e["efektif"] if tepe is None else max(tepe, e["efektif"])
        if tepe and tepe > 0:
            max_dd = min(max_dd, e["efektif"] / tepe - 1)

    return {
        "islem": len(islemler),
        "pnl": sum(pnl),
        "wr": len(kazanan) / len(islemler) * 100,
        "ev": sum(pnl) / len(islemler),
        "ort_kazanc": sum(kazanan) / len(kazanan) if kazanan else 0.0,
        "ort_kayip": sum(kaybeden) / len(kaybeden) if kaybeden else 0.0,
        "max_dd": abs(max_dd) * 100,
        "komisyon": sum(k["komisyon"] for k in kayitlar),
        "son_bakiye": equity[-1]["efektif"] if equity else None,
        "sebepler": {
            s: sum(1 for k in kayitlar if k["sebep"] == s)
            for s in sorted({k["sebep"] for k in kayitlar})
        },
    }
