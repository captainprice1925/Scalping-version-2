# -*- coding: utf-8 -*-
"""Bariyer yarışı simülatörü — canlı paper_trade.py kurallarının kopyası.

Canlı kurallar:
- Giriş piyasa emri: giriş kayması (GIRIS_SLIPPAGE_ORANI) + taker komisyon
- Seviyeler ham giriş fiyatından: SL 1.5 ATR, TP1 1.2 ATR, TP2 1.89 ATR, TP3 2.7 ATR
- Aynı mumda SL ve TP varsa SL önce (kötümser/gerçekçi)
- TP1 %40 kapatır, stop giriş fiyatına (BE) çekilir
- TP2 %30 kapatır, stop TP1'e çekilir
- TP3 kalanı kapatır
- 24 saatte kapanmayan işlem kapanış fiyatından ZAMAN ile kapanır

Çıktı birim notional başına net getiridir (pnl_pct); dolar karşılığı = pnl_pct × notional.
"""
import config

# Canlı config'den backtest parametre seti üretir. Testlerde/varyant
# karşılaştırmalarında kopya üzerinden değiştirilir; global config'e dokunulmaz.
def varsayilan_cfg():
    return {
        "BUTCE_SANAL": config.BUTCE_SANAL,
        "SL_ATR": config.SL_ATR * config.BARAJ_GENISLETME,
        "BE_ATR": config.BE_ATR * config.BARAJ_GENISLETME,
        "TP_ATR": config.TP_ATR * config.BARAJ_GENISLETME,
        "TP1_YUZDE": config.TP1_YUZDE,
        "TP2_YUZDE": config.TP2_YUZDE,
        "ZAMAN_EXIT_SAAT": config.ZAMAN_EXIT_SAAT_ETKIN,
        "GIRIS_KOMISYON_ORANI": config.GIRIS_KOMISYON_ORANI,
        "CIKIS_KOMISYON_ORANI": config.CIKIS_KOMISYON_ORANI,
        "GIRIS_SLIPPAGE_ORANI": config.GIRIS_SLIPPAGE_ORANI,
        "CIKIS_SLIPPAGE_ORANI": config.CIKIS_SLIPPAGE_ORANI,
        "MIN_EMA_DIST": config.MIN_EMA_DIST,
        "MAX_VOL_RATIO": config.MAX_VOL_RATIO,
        "MIN_ATR_PCT": config.MIN_ATR_PCT,
        "MAX_ATR_PCT": config.MAX_ATR_PCT,
        "MIN_SKOR": config.MIN_SKOR,
        "VOLUME_MULT": config.VOLUME_MULT,
        "RSI_LONG_MIN": config.RSI_LONG_MIN,
        "RSI_LONG_MAX": config.RSI_LONG_MAX,
        "RSI_SHORT_MIN": config.RSI_SHORT_MIN,
        "RSI_SHORT_MAX": config.RSI_SHORT_MAX,
        "BTC_REGIME_FILTRE": config.BTC_REGIME_FILTRE,
        "COOLDOWN_DAKIKA": config.COOLDOWN_DAKIKA,
        "COOLDOWN_BE_DAKIKA": config.COOLDOWN_BE_DAKIKA,
        "MAX_POZISYON": config.MAX_POZISYON,
        "MAX_AYNI_YON": config.MAX_AYNI_YON,
        "RISK_YUZDE_ISLEM": config.RISK_YUZDE_ISLEM,
        "MAX_TOPLAM_RISK_YUZDE": config.MAX_TOPLAM_RISK_YUZDE,
        "KALDIRAC": config.KALDIRAC,
        "MIN_ISLEM_MARJINI": config.MIN_ISLEM_MARJINI,
        "MAX_ISLEM_MARJINI": config.MAX_ISLEM_MARJINI,
        "MAX_ISLEM_MARJINI_ORAN": config.MAX_ISLEM_MARJINI_ORAN,
        "MAX_TOPLAM_MARJIN_YUZDE": config.MAX_TOPLAM_MARJIN_YUZDE,
        "GUNLUK_KAYIP_LIMITI": config.GUNLUK_KAYIP_LIMITI,
        "MAX_DRAWDOWN": config.MAX_DRAWDOWN,
        "DD_TOPARLANMA_ESIGI": config.DD_TOPARLANMA_ESIGI,
        "DD_SERT_DURDURMA": config.DD_SERT_DURDURMA,
        "DD_KURTARMA_RISK_ORANI": config.DD_KURTARMA_RISK_ORANI,
    }


def filtersiz_cfg():
    """V6.2/V6.3 filtreleri kapalı (eski davranış) — karşılaştırma için."""
    cfg = varsayilan_cfg()
    cfg.update(
        {
            "MIN_EMA_DIST": 0.0,
            "MAX_VOL_RATIO": float("inf"),
            "MIN_ATR_PCT": None,
            "MAX_ATR_PCT": None,
        }
    )
    return cfg


def v62_cfg():
    """Sadece V6.2 (ATR bandı yok) — 7-19 Kasım canlı doğrulamasıyla eşleştirme için."""
    cfg = varsayilan_cfg()
    cfg.update({"MIN_ATR_PCT": None, "MAX_ATR_PCT": None})
    return cfg


def atr_only_cfg():
    """ATR bandı korunur, V6.2'nin ema_dist tabanı kaldırılır."""
    cfg = varsayilan_cfg()
    cfg["MIN_EMA_DIST"] = 0.0
    return cfg


def maker_cfg(taban=None):
    """Limit/maker giriş: %0,02 komisyon, giriş kayması yok (dolum varsayımı)."""
    cfg = (taban or varsayilan_cfg()).copy()
    cfg["GIRIS_KOMISYON_ORANI"] = 0.0002
    cfg["GIRIS_SLIPPAGE_ORANI"] = 0.0
    return cfg


def eski_dd_cfg():
    """V6.3.2 öncesi kalıcı kilit: %20'de tam durdurma, toparlanma yok."""
    cfg = varsayilan_cfg()
    cfg["DD_SERT_DURDURMA"] = cfg["MAX_DRAWDOWN"]
    cfg["DD_TOPARLANMA_ESIGI"] = cfg["MAX_DRAWDOWN"]
    return cfg


def genis_cfg(oran=2.0, taban=None):
    """TP/SL mesafelerini taban cfg'ye göre `oran` katına çıkarır (baraj genişletme).

    Gerekçe: tur maliyeti (~16 bps) baraj mesafesinden bağımsız sabittir; çok
    dar barajlarda maliyet hedefin büyük kısmını yer. Bu varyant sadece
    karşılaştırma içindir, canlı kural değildir.

    Canlı kurallar `config.BARAJ_GENISLETME` ile zaten ölçekliyse bu çarpan
    onun üzerine biner (varsayılan 1.0 iken etkisi yoktur).

    `ZAMAN_EXIT_SAAT` de aynı oranda ölçeklenir; aksi halde geniş barajlar
    zaman çıkışına takılıp elma-armut karşılaştırması olur.
    """
    cfg = (taban or varsayilan_cfg()).copy()
    for anahtar in ("SL_ATR", "BE_ATR", "TP_ATR"):
        cfg[anahtar] = cfg[anahtar] * oran
    cfg["ZAMAN_EXIT_SAAT"] = max(1, int(round(cfg["ZAMAN_EXIT_SAAT"] * oran)))
    return cfg


def filtreli_skor(trend_long, ema_dist, volume_ratio, rsi, atr_pct, cfg):
    """faz2_sinyal.calculate_score_fatih ile birebir aynı mantık (parite testi var)."""
    if ema_dist < cfg["MIN_EMA_DIST"]:
        return 0, None
    if volume_ratio > cfg["MAX_VOL_RATIO"]:
        return 0, None
    alt = cfg.get("MIN_ATR_PCT")
    ust = cfg.get("MAX_ATR_PCT")
    if alt is not None and atr_pct < alt:
        return 0, None
    if ust is not None and atr_pct > ust:
        return 0, None

    skor = 0
    if trend_long:
        if ema_dist < 0.8:
            skor += 1
        if cfg["RSI_LONG_MIN"] <= rsi <= cfg["RSI_LONG_MAX"]:
            skor += 2
        if volume_ratio >= cfg["VOLUME_MULT"]:
            skor += 1
        return skor, ("LONG" if skor >= cfg["MIN_SKOR"] else None)

    if ema_dist < 0.8:
        skor += 1
    if cfg["RSI_SHORT_MIN"] <= rsi <= cfg["RSI_SHORT_MAX"]:
        skor += 2
    if volume_ratio >= cfg["VOLUME_MULT"]:
        skor += 1
    return skor, ("SHORT" if skor >= cfg["MIN_SKOR"] else None)


def giris_fill(ham, yon, cfg):
    kayma = cfg["GIRIS_SLIPPAGE_ORANI"]
    return ham * (1 - kayma) if yon == "SHORT" else ham * (1 + kayma)


def cikis_fill(ham, yon, cfg):
    kayma = cfg["CIKIS_SLIPPAGE_ORANI"]
    return ham * (1 + kayma) if yon == "SHORT" else ham * (1 - kayma)


def seviyeler(ham, yon, atr, cfg):
    if yon == "SHORT":
        return {
            "sl": ham + atr * cfg["SL_ATR"],
            "tp1": ham - atr * cfg["BE_ATR"],
            "tp2": ham - atr * cfg["TP_ATR"] * 0.7,
            "tp3": ham - atr * cfg["TP_ATR"],
        }
    return {
        "sl": ham - atr * cfg["SL_ATR"],
        "tp1": ham + atr * cfg["BE_ATR"],
        "tp2": ham + atr * cfg["TP_ATR"] * 0.7,
        "tp3": ham + atr * cfg["TP_ATR"],
    }


def parca_pnl(giris_fill_fiyat, ham_cikis, oran, yon, cfg):
    """Bir kısmi kapanışın notional oranı başına net getirisi."""
    cikis = cikis_fill(ham_cikis, yon, cfg)
    if yon == "SHORT":
        brut = (giris_fill_fiyat - cikis) / giris_fill_fiyat
    else:
        brut = (cikis - giris_fill_fiyat) / giris_fill_fiyat
    maliyet = cfg["GIRIS_KOMISYON_ORANI"] + cfg["CIKIS_KOMISYON_ORANI"]
    return oran * (brut - maliyet)


def islem_simule(df, i, yon, atr, cfg):
    """i barının kapanışından giriş yapıp sonraki barlarda bariyer yarışını oynatır.

    df: time/open/high/low/close kolonlu 1h veri (göstergeler önemli değil).
    Dönüş: pnl_pct (notional başına net), sebepler, giris/bitis zamanı, süre.
    """
    ham = float(df["close"].iat[i])
    giris = giris_fill(ham, yon, cfg)
    lv = seviyeler(ham, yon, atr, cfg)
    sl = lv["sl"]
    kalan = 1.0
    pnl = 0.0
    sebepler = []
    tp1_gecti = False
    tp2_gecti = False
    t0 = df["time"].iat[i]
    bitis = t0

    for j in range(i + 1, len(df)):
        o = float(df["open"].iat[j])
        h = float(df["high"].iat[j])
        l = float(df["low"].iat[j])
        c = float(df["close"].iat[j])
        t = df["time"].iat[j]

        if (t - t0).total_seconds() > cfg["ZAMAN_EXIT_SAAT"] * 3600:
            pnl += parca_pnl(giris, c, kalan, yon, cfg)
            sebepler.append("ZAMAN")
            kalan = 0.0
            bitis = t
            break

        if yon == "SHORT":
            if h >= sl:
                fiyat = max(o, sl)
                pnl += parca_pnl(giris, fiyat, kalan, yon, cfg)
                sebepler.append("BE" if tp1_gecti else "STOP")
                kalan = 0.0
                bitis = t
                break
            if l <= lv["tp1"] and not tp1_gecti:
                oran = min(cfg["TP1_YUZDE"] / 100, kalan)
                pnl += parca_pnl(giris, lv["tp1"], oran, yon, cfg)
                kalan -= oran
                sl = giris
                tp1_gecti = True
                sebepler.append("TP1")
                bitis = t
            if l <= lv["tp2"] and tp1_gecti and not tp2_gecti:
                oran = min(cfg["TP2_YUZDE"] / 100, kalan)
                pnl += parca_pnl(giris, lv["tp2"], oran, yon, cfg)
                kalan -= oran
                sl = lv["tp1"]
                tp2_gecti = True
                sebepler.append("TP2")
                bitis = t
            if l <= lv["tp3"] and tp1_gecti and kalan > 0:
                pnl += parca_pnl(giris, lv["tp3"], kalan, yon, cfg)
                kalan = 0.0
                sebepler.append("TP3")
                bitis = t
                break
        else:
            if l <= sl:
                fiyat = min(o, sl)
                pnl += parca_pnl(giris, fiyat, kalan, yon, cfg)
                sebepler.append("BE" if tp1_gecti else "STOP")
                kalan = 0.0
                bitis = t
                break
            if h >= lv["tp1"] and not tp1_gecti:
                oran = min(cfg["TP1_YUZDE"] / 100, kalan)
                pnl += parca_pnl(giris, lv["tp1"], oran, yon, cfg)
                kalan -= oran
                sl = giris
                tp1_gecti = True
                sebepler.append("TP1")
                bitis = t
            if h >= lv["tp2"] and tp1_gecti and not tp2_gecti:
                oran = min(cfg["TP2_YUZDE"] / 100, kalan)
                pnl += parca_pnl(giris, lv["tp2"], oran, yon, cfg)
                kalan -= oran
                sl = lv["tp1"]
                tp2_gecti = True
                sebepler.append("TP2")
                bitis = t
            if h >= lv["tp3"] and tp1_gecti and kalan > 0:
                pnl += parca_pnl(giris, lv["tp3"], kalan, yon, cfg)
                kalan = 0.0
                sebepler.append("TP3")
                bitis = t
                break

    if kalan > 0:
        # Veri sonuna kadar çözülmedi: son kapanıştan çık (raporlanır ve ayrılır)
        pnl += parca_pnl(giris, float(df["close"].iat[-1]), kalan, yon, cfg)
        sebepler.append("VERI_SONU")
        bitis = df["time"].iat[-1]

    return {
        "giris": giris,
        "ham_giris": ham,
        "seviyeler": lv,
        "pnl_pct": pnl,
        "sebepler": sebepler,
        "ilk_sebep": sebepler[0] if sebepler else None,
        "sebep": sebepler[-1] if sebepler else None,
        "giris_zaman": t0,
        "cikis_zaman": bitis,
        "sure_saat": (bitis - t0).total_seconds() / 3600,
        "tp1_gordu": tp1_gecti,
    }
