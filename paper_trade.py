from datetime import date, datetime, timedelta

import config
import state_store


class PaperTrade:
    """Gerçek emir göndermeyen, maliyet ve risk varsayımlı perpetual paper-trade motoru."""

    def __init__(self, telegram_func=None):
        self.telegram = telegram_func
        kayitli = state_store.state_yukle()
        if kayitli:
            self.bakiye = kayitli.get("bakiye", config.BUTCE_SANAL)
            self.pozisyonlar = kayitli.get("pozisyonlar", [])
            self.islem_gecmisi = kayitli.get("islem_gecmisi", [])
            self.cooldown = {
                symbol: datetime.fromisoformat(until)
                for symbol, until in kayitli.get("cooldown", {}).items()
            }
            self.gun_baslangic_bakiye = kayitli.get(
                "gun_baslangic_bakiye", config.BUTCE_SANAL
            )
            self.gun_tarihi = date.fromisoformat(
                kayitli.get("gun_tarihi", datetime.now().date().isoformat())
            )
            self.gunluk_limit_asildi = kayitli.get("gunluk_limit_asildi", False)
            self.gunluk_gerceklesen_pnl = kayitli.get("gunluk_gerceklesen_pnl", 0.0)
            self.peak_bakiye = kayitli.get("peak_bakiye", config.BUTCE_SANAL)
            self.drawdown_limit_asildi = kayitli.get("drawdown_limit_asildi", False)
            self._eski_state_tasima()
            print(f"✅ Kayıtlı state yüklendi (Bakiye: ${self.bakiye:.2f})")
        else:
            self.bakiye = config.BUTCE_SANAL
            self.pozisyonlar = []
            self.islem_gecmisi = []
            self.cooldown = {}
            self.gun_baslangic_bakiye = config.BUTCE_SANAL
            self.gun_tarihi = datetime.now().date()
            self.gunluk_limit_asildi = False
            self.gunluk_gerceklesen_pnl = 0.0
            self.peak_bakiye = config.BUTCE_SANAL
            self.drawdown_limit_asildi = False
            print("🆕 Yeni state başlatıldı")

    def _eski_state_tasima(self):
        """Önceki state dosyalarında bulunmayan V6 alanlarını güvenli varsayımlarla ekler."""
        for pozisyon in self.pozisyonlar:
            pozisyon.setdefault("notional", pozisyon["miktar"] * config.KALDIRAC)
            pozisyon.setdefault("giris_fiyat", pozisyon["entry"])
            pozisyon.setdefault("giris_komisyonu", 0.0)
            pozisyon.setdefault("son_fiyat", pozisyon["entry"])
            pozisyon.setdefault("tahmini_likidasyon", None)
            pozisyon.setdefault("son_fonlama_zamani", None)

    def _kaydet(self):
        state_store.state_kaydet(
            {
                "bakiye": self.bakiye,
                "pozisyonlar": self.pozisyonlar,
                "islem_gecmisi": self.islem_gecmisi,
                "cooldown": {
                    symbol: until.isoformat() for symbol, until in self.cooldown.items()
                },
                "gun_baslangic_bakiye": self.gun_baslangic_bakiye,
                "gun_tarihi": self.gun_tarihi.isoformat(),
                "gunluk_limit_asildi": self.gunluk_limit_asildi,
                "gunluk_gerceklesen_pnl": self.gunluk_gerceklesen_pnl,
                "peak_bakiye": self.peak_bakiye,
                "drawdown_limit_asildi": self.drawdown_limit_asildi,
            }
        )

    def _kalan_oran(self, pozisyon):
        return pozisyon["kalan_yuzde"] / 100

    def _kalan_marjin(self, pozisyon):
        return pozisyon["miktar"] * self._kalan_oran(pozisyon)

    def _kalan_notional(self, pozisyon):
        return pozisyon["notional"] * self._kalan_oran(pozisyon)

    def _giris_fiyati(self, fiyat, direction):
        if direction == "LONG":
            return fiyat * (1 + config.GIRIS_SLIPPAGE_ORANI)
        return fiyat * (1 - config.GIRIS_SLIPPAGE_ORANI)

    def _cikis_fiyati(self, fiyat, direction):
        if direction == "LONG":
            return fiyat * (1 - config.CIKIS_SLIPPAGE_ORANI)
        return fiyat * (1 + config.CIKIS_SLIPPAGE_ORANI)

    def _brut_pnl(self, pozisyon, ham_cikis_fiyati, yuzde=None):
        oran = self._kalan_oran(pozisyon) if yuzde is None else yuzde / 100
        notional = pozisyon["notional"] * oran
        giris = pozisyon["giris_fiyat"]
        cikis = self._cikis_fiyati(ham_cikis_fiyati, pozisyon["direction"])
        if pozisyon["direction"] == "LONG":
            return (cikis - giris) / giris * notional
        return (giris - cikis) / giris * notional

    def _tahmini_cikis_komisyonu(self, pozisyon, yuzde=None):
        oran = self._kalan_oran(pozisyon) if yuzde is None else yuzde / 100
        return pozisyon["notional"] * oran * config.CIKIS_KOMISYON_ORANI

    def tahmini_stop_riski(self, pozisyon, acilis_komisyonu_dahil=True):
        """Açık kalan miktarın mevcut stop seviyesinde tahmini parasal kaybı."""
        brut_pnl = self._brut_pnl(pozisyon, pozisyon["sl"])
        risk = max(0.0, -brut_pnl) + self._tahmini_cikis_komisyonu(pozisyon)
        if acilis_komisyonu_dahil:
            risk += pozisyon.get("giris_komisyonu", 0.0) * self._kalan_oran(pozisyon)
        return risk

    def _acik_pozisyon_degeri(self, pozisyon):
        son_fiyat = pozisyon.get("son_fiyat", pozisyon["entry"])
        return (
            self._kalan_marjin(pozisyon)
            + self._brut_pnl(pozisyon, son_fiyat)
            - self._tahmini_cikis_komisyonu(pozisyon)
        )

    def _efektif_bakiye_hesapla(self):
        return self.bakiye + sum(
            self._acik_pozisyon_degeri(pozisyon) for pozisyon in self.pozisyonlar
        )

    def _toplam_acik_risk(self):
        return sum(self.tahmini_stop_riski(pozisyon) for pozisyon in self.pozisyonlar)

    def fonlama_uygula(self, symbol, events):
        """Yeni Gate fonlama tahakkuklarını açık pozisyona bir kez uygular.

        Pozitif oran uzun pozisyonun ödeme yaptığı, kısa pozisyonun aldığı anlamına gelir.
        Fonlama değeri mevcut son fiyatla tahmin edilir; gerçek işlemlerde borsanın mark
        fiyatı ve hesap ekstresi otoritedir.
        """
        pozisyon = next(
            (item for item in self.pozisyonlar if item["symbol"] == symbol), None
        )
        if pozisyon is None:
            return

        acilis_ms = int(
            datetime.fromisoformat(pozisyon["acilis_zamani"]).timestamp() * 1000
        )
        son_fonlama = pozisyon.get("son_fonlama_zamani")
        for event in sorted(events, key=lambda item: item["timestamp"]):
            timestamp = event["timestamp"]
            oran = event["rate"]
            if timestamp <= acilis_ms or (
                son_fonlama is not None and timestamp <= son_fonlama
            ):
                continue

            mark_deger = (
                self._kalan_notional(pozisyon)
                * pozisyon.get("son_fiyat", pozisyon["entry"])
                / pozisyon["giris_fiyat"]
            )
            fonlama_pnl = -mark_deger * oran
            if pozisyon["direction"] == "SHORT":
                fonlama_pnl *= -1

            self.bakiye += fonlama_pnl
            self.gunluk_gerceklesen_pnl += fonlama_pnl
            self.islem_gecmisi.append(
                {
                    "symbol": pozisyon["symbol"],
                    "direction": pozisyon["direction"],
                    "entry": pozisyon["giris_fiyat"],
                    "exit": pozisyon.get("son_fiyat", pozisyon["entry"]),
                    "yuzde": pozisyon["kalan_yuzde"],
                    "sebep": "FONLAMA",
                    "skor": pozisyon.get("skor", 0),
                    "brut_pnl": fonlama_pnl,
                    "komisyon": 0.0,
                    "pnl": fonlama_pnl,
                    "fonlama_orani": oran,
                    "zaman": datetime.fromtimestamp(timestamp / 1000).isoformat(),
                }
            )
            pozisyon["son_fonlama_zamani"] = timestamp
            son_fonlama = timestamp

        self.peak_bakiye = max(self.peak_bakiye, self._efektif_bakiye_hesapla())
        self._max_drawdown_kontrol()
        self._kaydet()

    def gunluk_kontrol(self):
        bugun = datetime.now().date()
        if bugun != self.gun_tarihi:
            self.gun_tarihi = bugun
            self.gunluk_gerceklesen_pnl = 0.0
            self.gunluk_limit_asildi = False
            self.gun_baslangic_bakiye = self._efektif_bakiye_hesapla()
            self._kaydet()
            print(f"🌅 Yeni gün - başlangıç bakiye: ${self.gun_baslangic_bakiye:.2f}")

        gunluk_limit = self.gun_baslangic_bakiye * config.GUNLUK_KAYIP_LIMITI
        if max(0, -self.gunluk_gerceklesen_pnl) >= gunluk_limit:
            if not self.gunluk_limit_asildi:
                self.gunluk_limit_asildi = True
                self._kaydet()
                print(
                    "⛔ Günlük kayıp limiti aşıldı "
                    f"(-${max(0, -self.gunluk_gerceklesen_pnl):.2f} / ${gunluk_limit:.2f})"
                )
                if self.telegram:
                    self.telegram(
                        "⛔ <b>Günlük kayıp limiti aşıldı</b>\n"
                        f"📉 Bugünkü PnL: -${max(0, -self.gunluk_gerceklesen_pnl):.2f} "
                        f"/ ${gunluk_limit:.2f}\n🛑 Bugün yeni işlem açılmayacak"
                    )
            return True
        return False

    def _max_drawdown_kontrol(self):
        efektif = self._efektif_bakiye_hesapla()
        if efektif < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                self._kaydet()
                drawdown = (
                    (self.peak_bakiye - efektif) / self.peak_bakiye * 100
                    if self.peak_bakiye > 0
                    else 0
                )
                print(
                    f"⛔ MAX DRAWDOWN %{drawdown:.1f} - Efektif: ${efektif:.2f} "
                    f"/ Tepe: ${self.peak_bakiye:.2f}"
                )
                if self.telegram:
                    self.telegram(
                        f"⛔ <b>MAX DRAWDOWN %{drawdown:.1f}</b>\n"
                        f"💰 Efektif: ${efektif:.2f} / Tepe: ${self.peak_bakiye:.2f}\n"
                        "🛑 Yeni işlem açılmayacak"
                    )
            return True

        if self.drawdown_limit_asildi:
            self.drawdown_limit_asildi = False
            self._kaydet()
            print("✅ Drawdown eşiğin altına düştü - yeni işlemler yeniden açılabilir")
            if self.telegram:
                self.telegram("✅ Drawdown eşiğin altına düştü, yeni işlemler yeniden açılabilir")
        return False

    def akilli_sl_tp_hesapla(self, df, direction, atr, referans_fiyat=None):
        """Giriş fiyatına göre 1,5 ATR SL ve 1,2/1,89/2,7 ATR hedefleri üretir."""
        close = referans_fiyat if referans_fiyat is not None else df.iloc[-1]["close"]
        if atr is None or atr <= 0 or close is None or close <= 0:
            raise ValueError("Geçerli giriş fiyatı ve ATR gerekli")

        if direction == "LONG":
            sl = close - atr * config.SL_ATR
            tp1 = close + atr * config.BE_ATR
            tp2 = close + atr * config.TP_ATR * 0.7
            tp3 = close + atr * config.TP_ATR
        else:
            sl = close + atr * config.SL_ATR
            tp1 = close - atr * config.BE_ATR
            tp2 = close - atr * config.TP_ATR * 0.7
            tp3 = close - atr * config.TP_ATR

        risk = abs(close - sl)
        odul = abs(tp3 - close)
        return {
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": odul / risk if risk > 0 else 0,
            "sl_mesafe": atr * config.SL_ATR,
        }

    def _tahmini_likidasyon_fiyati(self, giris_fiyati, direction):
        """Bakım marjini hariç, izole 10× pozisyon için ihtiyatlı yaklaşık tasfiye seviyesi.

        Bu değer borsa tasfiye fiyatı değildir; gerçek emir uygulamasında borsa API'sinden alınmalıdır.
        """
        hareket = 1 / config.KALDIRAC
        if direction == "LONG":
            return giris_fiyati * (1 - hareket)
        return giris_fiyati * (1 + hareket)

    def _stop_likidasyon_guvenli_mi(self, levels, giris_fiyati, direction):
        likidasyon = self._tahmini_likidasyon_fiyati(giris_fiyati, direction)
        if direction == "LONG":
            return levels["sl"] > likidasyon * (1 + config.LIKIDASYON_TAMPON_YUZDE), likidasyon
        return levels["sl"] < likidasyon * (1 - config.LIKIDASYON_TAMPON_YUZDE), likidasyon

    def _pozisyon_boyutlandir(self, direction, entry, levels):
        giris_fiyati = self._giris_fiyati(entry, direction)
        cikis_fiyati = self._cikis_fiyati(levels["sl"], direction)
        fiyat_riski = abs(cikis_fiyati - giris_fiyati) / giris_fiyati
        maliyet_orani = config.GIRIS_KOMISYON_ORANI + config.CIKIS_KOMISYON_ORANI
        birim_notional_risk = fiyat_riski + maliyet_orani
        if birim_notional_risk <= 0:
            raise ValueError("Pozisyon riski hesaplanamadı")

        efektif_bakiye = self._efektif_bakiye_hesapla()
        toplam_risk_limiti = efektif_bakiye * config.MAX_TOPLAM_RISK_YUZDE
        mevcut_acik_risk = self._toplam_acik_risk()
        # Yeni işlem, efektif bakiyeyi giriş komisyonu, beklenen çıkış komisyonu
        # ve ilk fiyat kayması kadar azaltır. Toplam risk sınırı bu düşüşten sonra
        # da korunacak şekilde çözümlenir.
        acilis_etkisi_orani = (
            config.GIRIS_KOMISYON_ORANI
            + config.CIKIS_KOMISYON_ORANI
            + abs(cikis_fiyati - giris_fiyati) / giris_fiyati
        )
        tek_islem_notional_limiti = (
            efektif_bakiye * config.RISK_YUZDE_ISLEM / birim_notional_risk
        )
        toplam_risk_notional_limiti = (
            toplam_risk_limiti - mevcut_acik_risk
        ) / (birim_notional_risk + acilis_etkisi_orani * config.MAX_TOPLAM_RISK_YUZDE)
        if toplam_risk_notional_limiti <= 0:
            return None

        hesaplanan_notional = min(
            tek_islem_notional_limiti, toplam_risk_notional_limiti
        )
        hesaplanan_marjin = hesaplanan_notional / config.KALDIRAC
        kullanilan_marjin = sum(
            self._kalan_marjin(pozisyon) for pozisyon in self.pozisyonlar
        )
        musait_toplam_marjin = (
            efektif_bakiye * config.MAX_TOPLAM_MARJIN_YUZDE - kullanilan_marjin
        )
        marjin_limiti = min(
            config.MAX_ISLEM_MARJINI,
            efektif_bakiye * config.MAX_TOPLAM_MARJIN_YUZDE,
            musait_toplam_marjin,
        )
        marjin = min(hesaplanan_marjin, marjin_limiti)
        if marjin < config.MIN_ISLEM_MARJINI:
            return None

        notional = marjin * config.KALDIRAC
        giris_komisyonu = notional * config.GIRIS_KOMISYON_ORANI
        tahmini_stop_riski = notional * birim_notional_risk
        return {
            "marjin": marjin,
            "notional": notional,
            "giris_fiyati": giris_fiyati,
            "giris_komisyonu": giris_komisyonu,
            "tahmini_stop_riski": tahmini_stop_riski,
        }

    def cooldown_kontrol(self, symbol):
        if symbol not in self.cooldown:
            return False
        if datetime.now() < self.cooldown[symbol]:
            return True
        del self.cooldown[symbol]
        return False

    def cooldown_ekle(self, symbol, dakika=90):
        self.cooldown[symbol] = datetime.now() + timedelta(minutes=dakika)

    def islem_ac(self, symbol, direction, entry, atr, skor, df=None):
        if self.gunluk_kontrol():
            print(f"⛔ {symbol}: günlük kayıp limiti aktif")
            return False
        if self._max_drawdown_kontrol():
            print(f"⛔ {symbol}: max drawdown limiti aktif")
            return False
        if self.cooldown_kontrol(symbol):
            print(f"⏱ {symbol}: cooldown'da")
            return False
        if any(pozisyon["symbol"] == symbol for pozisyon in self.pozisyonlar):
            print(f"↩️ {symbol}: zaten açık pozisyon var")
            return False
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            print(f"⛔ {symbol}: max pozisyon sayısı ({config.MAX_POZISYON})")
            return False
        if (
            sum(1 for pozisyon in self.pozisyonlar if pozisyon["direction"] == direction)
            >= config.MAX_AYNI_YON
        ):
            print(f"⛔ {symbol}: max aynı yön limiti ({direction})")
            return False

        try:
            levels = self.akilli_sl_tp_hesapla(df, direction, atr, referans_fiyat=entry)
            boyut = self._pozisyon_boyutlandir(direction, entry, levels)
        except (TypeError, ValueError) as error:
            print(f"⛔ {symbol}: boyutlandırma hatası: {error}")
            return False
        if boyut is None:
            print(f"⛔ {symbol}: risk bütçesi minimum marjini karşılamıyor")
            return False

        likidasyon_guvenli, likidasyon = self._stop_likidasyon_guvenli_mi(
            levels, boyut["giris_fiyati"], direction
        )
        if not likidasyon_guvenli:
            print(f"⛔ {symbol}: stop tahmini likidasyona çok yakın")
            return False
        gereken_nakit = boyut["marjin"] + boyut["giris_komisyonu"]
        if self.bakiye < gereken_nakit:
            print(
                f"⛔ {symbol}: bakiye yetersiz "
                f"(${self.bakiye:.2f} < ${gereken_nakit:.2f})"
            )
            return False

        pozisyon = {
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "giris_fiyat": boyut["giris_fiyati"],
            "son_fiyat": entry,
            "atr": atr,
            "sl": levels["sl"],
            "tp1": levels["tp1"],
            "tp2": levels["tp2"],
            "tp3": levels["tp3"],
            "rr": levels["rr"],
            "skor": skor,
            "miktar": boyut["marjin"],
            "notional": boyut["notional"],
            "giris_komisyonu": boyut["giris_komisyonu"],
            "tahmini_stop_riski": boyut["tahmini_stop_riski"],
            "tahmini_likidasyon": likidasyon,
            "acilis_zamani": datetime.now().isoformat(),
            "son_fonlama_zamani": None,
            "tp1_tetiklendi": False,
            "tp2_tetiklendi": False,
            "kalan_yuzde": 100,
            "son_islenen_bar": None,
        }
        self.pozisyonlar.append(pozisyon)
        self.bakiye -= gereken_nakit
        self._kaydet()

        if self.telegram:
            self.telegram(
                f"✅ <b>{symbol} {direction}</b>\n"
                f"🎯 Skor: {skor}/4\n"
                f"💼 Marjin: ${boyut['marjin']:.2f} | Notional: ${boyut['notional']:.2f} "
                f"| x{config.KALDIRAC}\n"
                f"⚠️ Tahmini stop riski: ${boyut['tahmini_stop_riski']:.2f} "
                f"(%{config.RISK_YUZDE_ISLEM * 100:.1f} hedef)\n"
                f"📊 Efektif entry: {boyut['giris_fiyati']:.4f}\n"
                f"🛡 SL: {levels['sl']:.4f} | Tahmini liq: {likidasyon:.4f}\n"
                f"📦 TP1: {levels['tp1']:.4f} (%{config.TP1_YUZDE})\n"
                f"📦 TP2: {levels['tp2']:.4f} (%{config.TP2_YUZDE})\n"
                f"🎯 TP3: {levels['tp3']:.4f}"
            )
        return True

    def pozisyon_bars_guncelle(self, symbol, bars):
        """Kapanmış mumları bir kez, en güncel (oluşmakta olan) mumu ise kapanana
        kadar her turda yeniden işler; mum içi SL/TP dokunuşları kaçmaz."""
        pozisyon = next(
            (item for item in self.pozisyonlar if item["symbol"] == symbol), None
        )
        if pozisyon is None or bars is None or bars.empty:
            return

        acilis = datetime.fromisoformat(pozisyon["acilis_zamani"])
        son_islenen = pozisyon.get("son_islenen_bar")
        son_islenen_dt = (
            datetime.fromisoformat(son_islenen) if son_islenen is not None else None
        )
        rows = list(bars.iterrows())
        son_satir = len(rows) - 1
        for index, (_, row) in enumerate(rows):
            bar_dt = row["time"]
            if hasattr(bar_dt, "to_pydatetime"):
                bar_dt = bar_dt.to_pydatetime()
            elif not isinstance(bar_dt, datetime):
                bar_dt = datetime.fromisoformat(str(bar_dt))

            if bar_dt <= acilis or (son_islenen_dt is not None and bar_dt <= son_islenen_dt):
                continue

            self.pozisyon_guncelle(
                symbol,
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                bar_time=bar_dt.isoformat(),
            )
            if pozisyon not in self.pozisyonlar:
                break
            if index < son_satir:
                pozisyon["son_islenen_bar"] = bar_dt.isoformat()
                son_islenen_dt = bar_dt
            # Son satır hâlâ oluşmakta olan mumdur; "işlendi" işaretlenmez ki
            # sonraki turda kapanmış haliyle yeniden değerlendirilebilsin.
        self._kaydet()

    def _tp1_isle(self, pozisyon):
        if pozisyon["tp1_tetiklendi"]:
            return
        self.pozisyon_kapat(pozisyon, pozisyon["tp1"], config.TP1_YUZDE, "TP1")
        if pozisyon in self.pozisyonlar:
            pozisyon["sl"] = pozisyon["entry"]
            pozisyon["tp1_tetiklendi"] = True

    def _tp2_isle(self, pozisyon):
        if pozisyon["tp2_tetiklendi"]:
            return
        self._tp1_isle(pozisyon)
        if pozisyon not in self.pozisyonlar:
            return
        self.pozisyon_kapat(pozisyon, pozisyon["tp2"], config.TP2_YUZDE, "TP2")
        if pozisyon in self.pozisyonlar:
            pozisyon["sl"] = pozisyon["tp1"]
            pozisyon["tp2_tetiklendi"] = True

    def _tp3_isle(self, pozisyon):
        self._tp2_isle(pozisyon)
        if pozisyon in self.pozisyonlar:
            self.pozisyon_kapat(
                pozisyon, pozisyon["tp3"], pozisyon["kalan_yuzde"], "TP3"
            )

    def pozisyon_guncelle(self, symbol, o, h, l, c, bar_time=None):
        """Tek mumla SL/TP kontrolü; aynı mumda SL ve TP varsa SL önce işlenir."""
        for pozisyon in self.pozisyonlar[:]:
            if pozisyon["symbol"] != symbol:
                continue
            pozisyon["son_fiyat"] = c

            if bar_time is not None:
                try:
                    acilis = datetime.fromisoformat(pozisyon["acilis_zamani"])
                    if (
                        datetime.fromisoformat(bar_time) - acilis
                    ).total_seconds() > config.ZAMAN_EXIT_SAAT * 3600:
                        self.pozisyon_kapat(
                            pozisyon, c, pozisyon["kalan_yuzde"], "ZAMAN"
                        )
                        continue
                except (TypeError, ValueError):
                    pass

            if pozisyon["direction"] == "LONG":
                if l <= pozisyon["sl"]:
                    self.pozisyon_kapat(
                        pozisyon,
                        min(o, pozisyon["sl"]),
                        pozisyon["kalan_yuzde"],
                        "BE" if pozisyon["tp1_tetiklendi"] else "STOP",
                    )
                    continue
                if h >= pozisyon["tp3"]:
                    self._tp3_isle(pozisyon)
                    continue
                if h >= pozisyon["tp2"]:
                    self._tp2_isle(pozisyon)
                    continue
                if h >= pozisyon["tp1"]:
                    self._tp1_isle(pozisyon)
                    continue
            else:
                if h >= pozisyon["sl"]:
                    self.pozisyon_kapat(
                        pozisyon,
                        max(o, pozisyon["sl"]),
                        pozisyon["kalan_yuzde"],
                        "BE" if pozisyon["tp1_tetiklendi"] else "STOP",
                    )
                    continue
                if l <= pozisyon["tp3"]:
                    self._tp3_isle(pozisyon)
                    continue
                if l <= pozisyon["tp2"]:
                    self._tp2_isle(pozisyon)
                    continue
                if l <= pozisyon["tp1"]:
                    self._tp1_isle(pozisyon)
                    continue

        self.peak_bakiye = max(self.peak_bakiye, self._efektif_bakiye_hesapla())
        self._max_drawdown_kontrol()
        self._kaydet()

    def pozisyon_kapat(self, pozisyon, ham_cikis_fiyati, yuzde, sebep):
        if yuzde <= 0 or pozisyon not in self.pozisyonlar:
            return
        yuzde = min(yuzde, pozisyon["kalan_yuzde"])
        marjin = pozisyon["miktar"] * (yuzde / 100)
        notional = pozisyon["notional"] * (yuzde / 100)
        cikis_fiyati = self._cikis_fiyati(ham_cikis_fiyati, pozisyon["direction"])
        brut_pnl = self._brut_pnl(pozisyon, ham_cikis_fiyati, yuzde=yuzde)
        cikis_komisyonu = notional * config.CIKIS_KOMISYON_ORANI
        giris_komisyon_payi = pozisyon.get("giris_komisyonu", 0.0) * (yuzde / 100)
        net_pnl = brut_pnl - cikis_komisyonu - giris_komisyon_payi

        # Açılış komisyonu zaten pozisyon açılırken bakiyeden düşülmüştür.
        self.bakiye += marjin + brut_pnl - cikis_komisyonu
        self.gunluk_gerceklesen_pnl += net_pnl
        self.islem_gecmisi.append(
            {
                "symbol": pozisyon["symbol"],
                "direction": pozisyon["direction"],
                "entry": pozisyon["giris_fiyat"],
                "exit": cikis_fiyati,
                "yuzde": yuzde,
                "sebep": sebep,
                "skor": pozisyon.get("skor", 0),
                "brut_pnl": brut_pnl,
                "komisyon": giris_komisyon_payi + cikis_komisyonu,
                "pnl": net_pnl,
                "zaman": datetime.now().isoformat(),
            }
        )

        tam_kapanis = pozisyon["kalan_yuzde"] - yuzde <= 0
        if tam_kapanis:
            if sebep == "STOP":
                self.cooldown_ekle(pozisyon["symbol"], dakika=config.COOLDOWN_DAKIKA)
            elif sebep == "BE":
                self.cooldown_ekle(pozisyon["symbol"], dakika=config.COOLDOWN_BE_DAKIKA)

        if self.telegram:
            emoji = "✅" if net_pnl > 0 else "❌"
            kalan = pozisyon["kalan_yuzde"] - yuzde
            self.telegram(
                f"{emoji} <b>{pozisyon['symbol']} {sebep}</b> (%{yuzde:.0f})\n"
                f"💰 Exit: {cikis_fiyati:.4f}\n📈 Net PnL: ${net_pnl:+.2f}\n"
                f"💳 Komisyon: ${giris_komisyon_payi + cikis_komisyonu:.3f}"
                + (f"\n📦 Kalan: %{kalan:.0f}" if kalan > 0 else "")
            )

        pozisyon["kalan_yuzde"] -= yuzde
        if pozisyon["kalan_yuzde"] <= 0:
            self.pozisyonlar.remove(pozisyon)
        self.peak_bakiye = max(self.peak_bakiye, self._efektif_bakiye_hesapla())
        self._kaydet()

    def rapor(self):
        print("\n" + "=" * 60 + "\n📊 PAPER TRADE V6 RAPORU\n" + "=" * 60)
        islemler = [i for i in self.islem_gecmisi if i["sebep"] != "FONLAMA"]
        fonlama_pnl = sum(i["pnl"] for i in self.islem_gecmisi if i["sebep"] == "FONLAMA")
        toplam = len(islemler)
        kazanan = sum(1 for islem in islemler if islem["pnl"] > 0)
        pnl = sum(islem["pnl"] for islem in self.islem_gecmisi)
        efektif = self._efektif_bakiye_hesapla()
        drawdown = (
            (self.peak_bakiye - efektif) / self.peak_bakiye * 100
            if self.peak_bakiye > 0
            else 0
        )
        print(
            f"💰 Nakit: ${self.bakiye:.2f}\n"
            f"💎 Mark-to-market efektif: ${efektif:.2f}\n"
            f"📈 Pozisyon: {len(self.pozisyonlar)}\n"
            f"⚠️ Açık stop riski: ${self._toplam_acik_risk():.2f}\n"
            f"📉 Drawdown: %{drawdown:.1f}\n"
            f"📊 İşlem: {toplam} (W:{kazanan} L:{toplam - kazanan})"
        )
        if toplam > 0:
            print(f"🎯 Win rate: %{kazanan / toplam * 100:.1f}")
        print(f"💵 Net PnL: ${pnl:+.2f} (fonlama: ${fonlama_pnl:+.2f})\n" + "=" * 60)
