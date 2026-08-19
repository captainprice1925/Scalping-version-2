import json
from datetime import datetime, timedelta, date
import config
import state_store

class PaperTrade:
    def __init__(self, telegram_func=None):
        self.telegram = telegram_func
        kayitli = state_store.state_yukle()
        if kayitli:
            self.bakiye = kayitli.get('bakiye', config.BUTCE_SANAL)
            self.pozisyonlar = kayitli.get('pozisyonlar', [])
            self.islem_gecmisi = kayitli.get('islem_gecmisi', [])
            self.cooldown = {s: datetime.fromisoformat(d) for s, d in kayitli.get('cooldown', {}).items()}
            self.gun_baslangic_bakiye = kayitli.get('gun_baslangic_bakiye', config.BUTCE_SANAL)
            self.gun_tarihi = date.fromisoformat(kayitli.get('gun_tarihi', datetime.now().date().isoformat()))
            self.gunluk_limit_asildi = kayitli.get('gunluk_limit_asildi', False)
            self.gunluk_gerceklesen_pnl = kayitli.get('gunluk_gerceklesen_pnl', 0.0)
            self.peak_bakiye = kayitli.get('peak_bakiye', config.BUTCE_SANAL)
            self.drawdown_limit_asildi = kayitli.get('drawdown_limit_asildi', False)
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

    def _kaydet(self):
        state_store.state_kaydet({
            'bakiye': self.bakiye,
            'pozisyonlar': self.pozisyonlar,
            'islem_gecmisi': self.islem_gecmisi,
            'cooldown': {s: d.isoformat() for s, d in self.cooldown.items()},
            'gun_baslangic_bakiye': self.gun_baslangic_bakiye,
            'gun_tarihi': self.gun_tarihi.isoformat(),
            'gunluk_limit_asildi': self.gunluk_limit_asildi,
            'gunluk_gerceklesen_pnl': self.gunluk_gerceklesen_pnl,
            'peak_bakiye': self.peak_bakiye,
            'drawdown_limit_asildi': self.drawdown_limit_asildi,
        })

    def _efektif_bakiye_hesapla(self):
        pozisyondaki_para = sum(poz['miktar'] * (poz['kalan_yuzde'] / 100) for poz in self.pozisyonlar)
        return self.bakiye + pozisyondaki_para

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
                print(f"⛔ Günlük kayıp limiti aşıldı (-${max(0, -self.gunluk_gerceklesen_pnl):.2f} / ${gunluk_limit:.2f}) - bugün yeni işlem yok")
                if self.telegram:
                    self.telegram(f"⛔ <b>Günlük kayıp limiti aşıldı</b>\n📉 Bugünkü PnL: -${max(0, -self.gunluk_gerceklesen_pnl):.2f} / ${gunluk_limit:.2f}\n🛑 Bugün yeni işlem açılmayacak")
            return True
        return False

    def _max_drawdown_kontrol(self):
        efektif = self._efektif_bakiye_hesapla()
        if efektif < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                self._kaydet()
                dd = (self.peak_bakiye - efektif) / self.peak_bakiye * 100 if self.peak_bakiye > 0 else 0
                print(f"⛔ MAX DRAWDOWN %{dd:.1f} - Efektif: ${efektif:.2f} / Tepe: ${self.peak_bakiye:.2f} - yeni işlem açılmıyor")
                if self.telegram:
                    self.telegram(f"⛔ <b>MAX DRAWDOWN %{dd:.1f}</b>\n💰 Efektif: ${efektif:.2f} / Tepe: ${self.peak_bakiye:.2f}\n🛑 Yeni işlem açılmayacak (açık pozisyonlar yönetilmeye devam edecek)")
            return True
        else:
            if self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = False
                self._kaydet()
                print("✅ Drawdown eşiğin altına düştü - yeni işlemler yeniden açılabilir")
                if self.telegram:
                    self.telegram("✅ Drawdown eşiğin altına düştü, yeni işlemler yeniden açılabilir")
            return False

    def akilli_sl_tp_hesapla(self, df, direction, atr, referans_fiyat=None):
        """SL 1.5 ATR / TP1 1.2 (kademeli %40) / TP2 1.89 (%30) / TP3 2.7 (kalan)
        Seviyeler giriş (canlı) fiyatına göre hesaplanır."""
        close = referans_fiyat if referans_fiyat is not None else df.iloc[-1]['close']

        sl_atr = config.SL_ATR
        tp_atr = config.TP_ATR
        be_atr = config.BE_ATR

        if direction == "LONG":
            sl = close - atr * sl_atr
            tp1 = close + atr * be_atr
            tp2 = close + atr * tp_atr * 0.7
            tp3 = close + atr * tp_atr
        else:
            sl = close + atr * sl_atr
            tp1 = close - atr * be_atr
            tp2 = close - atr * tp_atr * 0.7
            tp3 = close - atr * tp_atr

        risk = abs(close - sl)
        odul = abs(tp3 - close)
        rr = odul / risk if risk > 0 else 1.8

        return {
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'rr': rr, 'sl_mesafe': atr * sl_atr,
            'analiz': {'sl_atr': f"{sl_atr}", 'tp_atr': f"{tp_atr}", 'be_atr': f"{be_atr}"}
        }

    def cooldown_kontrol(self, symbol):
        if symbol not in self.cooldown: return False
        if datetime.now() < self.cooldown[symbol]: return True
        del self.cooldown[symbol]
        return False

    def cooldown_ekle(self, symbol, dakika=90):
        self.cooldown[symbol] = datetime.now() + timedelta(minutes=dakika)

    def islem_ac(self, symbol, direction, entry, atr, skor, df=None):
        if self.gunluk_kontrol():
            print(f"⛔ {symbol}: günlük kayıp limiti aktif"); return False
        if self._max_drawdown_kontrol():
            print(f"⛔ {symbol}: max drawdown limiti aktif"); return False
        if self.cooldown_kontrol(symbol):
            print(f"⏱ {symbol}: cooldown'da"); return False
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol:
                print(f"↩️ {symbol}: zaten açık pozisyon var"); return False
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            print(f"⛔ {symbol}: max pozisyon sayısı ({config.MAX_POZISYON})"); return False
        if sum(1 for p in self.pozisyonlar if p['direction'] == direction) >= config.MAX_AYNI_YON:
            print(f"⛔ {symbol}: max aynı yön limiti ({direction})"); return False
        if self.bakiye < config.ISLEM_BASINA:
            print(f"⛔ {symbol}: bakiye yetersiz (${self.bakiye:.2f} < ${config.ISLEM_BASINA})"); return False

        levels = self.akilli_sl_tp_hesapla(df, direction, atr, referans_fiyat=entry)

        pozisyon = {
            'symbol': symbol, 'direction': direction, 'entry': entry, 'atr': atr,
            'sl': levels['sl'], 'tp1': levels['tp1'], 'tp2': levels['tp2'], 'tp3': levels['tp3'],
            'rr': levels['rr'], 'skor': skor, 'miktar': config.ISLEM_BASINA,
            'acilis_zamani': datetime.now().isoformat(),
            'tp1_tetiklendi': False, 'tp2_tetiklendi': False, 'kalan_yuzde': 100,
            'son_islenen_bar': None
        }

        self.pozisyonlar.append(pozisyon)
        self.bakiye -= config.ISLEM_BASINA

        if self.telegram:
            self.telegram(
                f"✅ <b>{symbol} {direction}</b>\n"
                f"🎯 Skor: {skor}/4\n"
                f"💰 ${config.ISLEM_BASINA} x{config.KALDIRAC}\n"
                f"📊 Entry: {entry:.4f}\n"
                f"🛡 SL: {levels['sl']:.4f} ({config.SL_ATR} ATR)\n"
                f"📦 TP1: {levels['tp1']:.4f} (%{config.TP1_YUZDE})\n"
                f"📦 TP2: {levels['tp2']:.4f} (%{config.TP2_YUZDE})\n"
                f"🎯 TP3: {levels['tp3']:.4f} (kalan %{100 - config.TP1_YUZDE - config.TP2_YUZDE})\n"
                f"📈 RR: {levels['rr']:.2f}"
            )
        self._kaydet()
        return True

    def pozisyon_bars_guncelle(self, symbol, bars):
        """bars: 'time','open','high','low','close' kolonlu DataFrame (kronolojik sıralı).
        Her mum sırayla işlenir; işlenen mumlar son_islenen_bar ile takip edilir."""
        poz = next((p for p in self.pozisyonlar if p['symbol'] == symbol), None)
        if poz is None or bars is None or bars.empty: return
        son = poz.get('son_islenen_bar')
        for _, row in bars.iterrows():
            t = row['time']
            t_iso = t.isoformat() if hasattr(t, 'isoformat') else str(t)
            if son is not None and t_iso <= son: continue
            self.pozisyon_guncelle(symbol, row['open'], row['high'], row['low'], row['close'], bar_time=t_iso)
            poz['son_islenen_bar'] = t_iso
            if poz not in self.pozisyonlar: break
        self._kaydet()

    def pozisyon_guncelle(self, symbol, o, h, l, c, bar_time=None):
        """Tek bir mumun open/high/low/close'u ile SL/TP kontrolü.
        Aynı mumda hem SL hem TP tetiklenirse SL önce işlenir (muhafazakâr)."""
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol: continue
            direction = poz['direction']

            # Zaman çıkışı: pozisyon çok uzun süredir açık ve hiçbir seviye tetiklenmedi
            if bar_time is not None:
                try:
                    acilis = datetime.fromisoformat(poz['acilis_zamani'])
                    if (datetime.fromisoformat(bar_time) - acilis).total_seconds() > config.ZAMAN_EXIT_SAAT * 3600:
                        self.pozisyon_kapat(poz, c, poz['kalan_yuzde'], "ZAMAN")
                        continue
                except (ValueError, TypeError):
                    pass

            if direction == "LONG":
                # SL önce: fitne (low) veya gap (açılış SL altında)
                if l <= poz['sl']:
                    exit_fiyat = min(o, poz['sl'])
                    sebep = "BE" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, exit_fiyat, poz['kalan_yuzde'], sebep); continue
                if h >= poz['tp3']:
                    self.pozisyon_kapat(poz, poz['tp3'], poz['kalan_yuzde'], "TP3"); continue
                if h >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    # geniş bar: TP1 kısmisi de atlandıysa önce onu işle
                    if not poz['tp1_tetiklendi']:
                        self.pozisyon_kapat(poz, poz['tp1'], config.TP1_YUZDE, "TP1")
                        poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True
                    self.pozisyon_kapat(poz, poz['tp2'], config.TP2_YUZDE, "TP2")
                    poz['sl'] = poz['tp1']; poz['tp2_tetiklendi'] = True
                    self._kaydet(); continue
                if h >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, poz['tp1'], config.TP1_YUZDE, "TP1")
                    poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True
                    self._kaydet(); continue
            else:
                if h >= poz['sl']:
                    exit_fiyat = max(o, poz['sl'])
                    sebep = "BE" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, exit_fiyat, poz['kalan_yuzde'], sebep); continue
                if l <= poz['tp3']:
                    self.pozisyon_kapat(poz, poz['tp3'], poz['kalan_yuzde'], "TP3"); continue
                if l <= poz['tp2'] and not poz['tp2_tetiklendi']:
                    if not poz['tp1_tetiklendi']:
                        self.pozisyon_kapat(poz, poz['tp1'], config.TP1_YUZDE, "TP1")
                        poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True
                    self.pozisyon_kapat(poz, poz['tp2'], config.TP2_YUZDE, "TP2")
                    poz['sl'] = poz['tp1']; poz['tp2_tetiklendi'] = True
                    self._kaydet(); continue
                if l <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, poz['tp1'], config.TP1_YUZDE, "TP1")
                    poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True
                    self._kaydet(); continue

    def _slippage_uygula(self, fiyat, direction):
        return fiyat * (1 + config.SLIPPAGE) if direction == "LONG" else fiyat * (1 - config.SLIPPAGE)

    def pozisyon_kapat(self, poz, exit_price, yuzde, sebep):
        if yuzde <= 0 or poz not in self.pozisyonlar: return
        direction = poz['direction']; entry = poz['entry']; miktar = poz['miktar'] * (yuzde / 100)
        entry = self._slippage_uygula(entry, direction)
        exit_price = self._slippage_uygula(exit_price, "LONG" if direction == "SHORT" else "SHORT")
        pnl = (exit_price - entry) / entry * miktar * config.KALDIRAC if direction == "LONG" else (entry - exit_price) / entry * miktar * config.KALDIRAC
        komisyon = miktar * config.KALDIRAC * config.KOMISYON * 2  # komisyon pozisyon büyüklüğü (margin x kaldıraç) üzerinden
        net_pnl = pnl - komisyon
        self.bakiye += miktar + net_pnl
        self.gunluk_gerceklesen_pnl += net_pnl
        self.peak_bakiye = max(self.peak_bakiye, self.bakiye)
        self.islem_gecmisi.append({'symbol': poz['symbol'], 'direction': direction, 'entry': entry, 'exit': exit_price, 'yuzde': yuzde, 'sebep': sebep, 'skor': poz.get('skor', 0), 'pnl': net_pnl, 'zaman': datetime.now().isoformat()})
        tam_kapanis = poz['kalan_yuzde'] - yuzde <= 0
        if tam_kapanis:
            if sebep == "STOP":
                self.cooldown_ekle(poz['symbol'], dakika=config.COOLDOWN_DAKIKA)
            elif sebep == "BE":
                self.cooldown_ekle(poz['symbol'], dakika=config.COOLDOWN_BE_DAKIKA)
        if self.telegram:
            emoji = "✅" if net_pnl > 0 else "❌"
            kalan = poz['kalan_yuzde'] - yuzde
            self.telegram(f"{emoji} <b>{poz['symbol']} {sebep}</b> (%{yuzde:.0f})\n💰 Exit: {exit_price:.4f}\n📈 PnL: ${net_pnl:+.2f}" + (f"\n📦 Kalan: %{kalan:.0f}" if kalan > 0 else ""))
        poz['kalan_yuzde'] -= yuzde
        if poz['kalan_yuzde'] <= 0:
            try: self.pozisyonlar.remove(poz)
            except: pass
        self._kaydet()

    def rapor(self):
        print("\n" + "="*60 + "\n📊 PAPER TRADE V5 RAPORU\n" + "="*60)
        toplam = len(self.islem_gecmisi); kaz = sum(1 for i in self.islem_gecmisi if i['pnl'] > 0); pnl = sum(i['pnl'] for i in self.islem_gecmisi)
        efektif = self._efektif_bakiye_hesapla(); dd = (self.peak_bakiye - efektif) / self.peak_bakiye * 100 if self.peak_bakiye > 0 else 0
        print(f"💰 Bakiye: ${self.bakiye:.2f}\n💎 Efektif: ${efektif:.2f}\n📈 Pozisyon: {len(self.pozisyonlar)}\n📉 Drawdown: %{dd:.1f}\n📊 İşlem: {toplam} (W:{kaz} L:{toplam-kaz})")
        if toplam > 0: print(f"🎯 Win rate: %{kaz/toplam*100:.1f}")
        print(f"💵 PnL: ${pnl:+.2f}\n" + "="*60)
