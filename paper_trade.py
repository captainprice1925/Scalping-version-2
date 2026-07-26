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
        pozisyondaki_para = sum(
            poz['miktar'] * (poz['kalan_yuzde'] / 100) 
            for poz in self.pozisyonlar
        )
        return self.bakiye + pozisyondaki_para
    
    def gunluk_kontrol(self):
        bugun = datetime.now().date()
        if bugun != self.gun_tarihi:
            self.gun_tarihi = bugun
            self.gunluk_gerceklesen_pnl = 0.0
            self.gunluk_limit_asildi = False
            self._kaydet()
        
        gunluk_limit = config.BUTCE_SANAL * config.GUNLUK_KAYIP_LIMITI
        gunluk_kayip = max(0, -self.gunluk_gerceklesen_pnl)
        
        if gunluk_kayip >= gunluk_limit:
            if not self.gunluk_limit_asildi:
                self.gunluk_limit_asildi = True
                if self.telegram:
                    self.telegram(f"🛑 <b>GÜNLÜK KAYIP LİMİTİ</b>\n📉 Kayıp: ${gunluk_kayip:.2f}")
                self._kaydet()
            return True
        return False
    
    def _max_drawdown_kontrol(self):
        efektif_bakiye = self._efektif_bakiye_hesapla()
        if efektif_bakiye < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                if self.telegram:
                    self.telegram(f"⚠️ <b>MAX DRAWDOWN</b>\n💰 Efektif: ${efektif_bakiye:.2f}")
                self._kaydet()
            return True
        else:
            if self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = False
                if self.telegram:
                    self.telegram(f"✅ <b>DRAWDOWN TOPARLANDI</b>")
                self._kaydet()
            return False
    
    def akilli_sl_tp_hesapla(self, df, direction, atr):
        row = df.iloc[-1]
        close = row['close']
        
        vol_ratio = row.get('atr_pct', 2.0) / 2.0
        vol_multiplier = max(0.7, min(1.5, vol_ratio))
        
        momentum = abs(row.get('rsi', 50) - 50) / 50
        momentum_multiplier = 1.0 + momentum * 0.3
        
        rsi = row.get('rsi', 50)
        rsi_factor = 1.0
        if (direction == "LONG" and rsi < 30) or (direction == "SHORT" and rsi > 70):
            rsi_factor = 1.2
        
        vol_confirm = row.get('volume_ratio', 1.0)
        volume_multiplier = min(1.3, vol_confirm)
        
        adx = row.get('adx', 20)
        trend_multiplier = 1.0 + min(0.3, (adx - 20) / 100)
        
        sl_atr_multiplier = 1.5 * vol_multiplier
        sl_atr_multiplier = max(config.SL_MIN_ATR, min(config.SL_MAX_ATR, sl_atr_multiplier))
        sl_mesafe = atr * sl_atr_multiplier
        
        tp_base = 3.0
        tp_multiplier = tp_base * momentum_multiplier * rsi_factor * volume_multiplier * trend_multiplier
        tp_multiplier = max(config.TP_MIN_ATR, min(config.TP_MAX_ATR, tp_multiplier))
        
        tp1_mult = tp_multiplier * 0.33
        tp2_mult = tp_multiplier * 0.66
        tp3_mult = tp_multiplier
        
        if direction == "LONG":
            sl = close - sl_mesafe
            tp1 = close + atr * tp1_mult
            tp2 = close + atr * tp2_mult
            tp3 = close + atr * tp3_mult
        else:
            sl = close + sl_mesafe
            tp1 = close - atr * tp1_mult
            tp2 = close - atr * tp2_mult
            tp3 = close - atr * tp3_mult
        
        risk = abs(close - sl)
        odul = abs(tp3 - close)
        rr = odul / risk if risk > 0 else 0
        
        return {
            'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'rr': rr, 'sl_mesafe': sl_mesafe,
            'analiz': {
                'vol': f"{vol_multiplier:.2f}",
                'mom': f"{momentum_multiplier:.2f}",
                'rsi': f"{rsi_factor:.2f}",
                'trend': f"{trend_multiplier:.2f}",
                'sl_atr': f"{sl_atr_multiplier:.2f}",
                'tp_atr': f"{tp_multiplier:.2f}"
            }
        }
    
    def cooldown_kontrol(self, symbol):
        if symbol not in self.cooldown:
            return False
        if datetime.now() < self.cooldown[symbol]:
            return True
        del self.cooldown[symbol]
        return False
    
    def cooldown_ekle(self, symbol, dakika=60):
        self.cooldown[symbol] = datetime.now() + timedelta(minutes=dakika)
    
    def islem_ac(self, symbol, direction, entry, atr, skor, df=None):
        if self.gunluk_kontrol(): return False
        if self._max_drawdown_kontrol(): return False
        if self.cooldown_kontrol(symbol): return False
        
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol:
                return False
        
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            return False
        
        if self.bakiye < config.ISLEM_BASINA:
            return False
        
        pozisyon_tutar = config.ISLEM_BASINA
        
        if df is not None and config.AKILLI_SL_TP:
            levels = self.akilli_sl_tp_hesapla(df, direction, atr)
            akilli = True
        else:
            sl_mesafe = atr * 1.5
            if direction == "LONG":
                sl = entry - sl_mesafe
                tp1 = entry + atr * 1.0
                tp2 = entry + atr * 2.0
                tp3 = entry + atr * 3.0
            else:
                sl = entry + sl_mesafe
                tp1 = entry - atr * 1.0
                tp2 = entry - atr * 2.0
                tp3 = entry - atr * 3.0
            risk = abs(entry - sl)
            odul = abs(tp3 - entry)
            rr = odul / risk if risk > 0 else 0
            levels = {'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'rr': rr, 'analiz': {}}
            akilli = False
        
        pozisyon = {
            'symbol': symbol,
            'direction': direction,
            'entry': entry,
            'atr': atr,
            'sl': levels['sl'],
            'tp1': levels['tp1'],
            'tp2': levels['tp2'],
            'tp3': levels['tp3'],
            'rr': levels['rr'],
            'skor': skor,
            'miktar': pozisyon_tutar,
            'acilis_zamani': datetime.now().isoformat(),
            'tp1_tetiklendi': False,
            'tp2_tetiklendi': False,
            'kalan_yuzde': 100,
            'akilli': akilli
        }
        
        self.pozisyonlar.append(pozisyon)
        self.bakiye -= pozisyon_tutar
        
        if self.telegram:
            analiz = ""
            if akilli:
                a = levels['analiz']
                analiz = f"\n🧠 Vol:{a['vol']} Mom:{a['mom']} RSI:{a['rsi']} Trend:{a['trend']}\n   SL:{a['sl_atr']}ATR TP:{a['tp_atr']}ATR"
            
            self.telegram(
                f"✅ <b>{symbol} {direction}</b>\n\n"
                f"🎯 Skor: {skor}/10\n"
                f"💰 $10 (sabit)\n"
                f"📊 Entry: {entry:.4f}\n"
                f"🛡️ SL: {levels['sl']:.4f}\n"
                f"🎯 TP1: {levels['tp1']:.4f} → SL=Entry\n"
                f"🎯 TP2: {levels['tp2']:.4f} → SL=TP1\n"
                f"🎯 TP3: {levels['tp3']:.4f} → %100\n"
                f"📈 RR: {levels['rr']:.2f}{analiz}"
            )
        
        self._kaydet()
        return True
    
    def pozisyon_guncelle(self, symbol, current_price):
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol:
                continue
            
            direction = poz['direction']
            
            if direction == "LONG":
                if current_price >= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3")
                    continue
                
                if current_price >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    eski_sl = poz['sl']
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    if self.telegram:
                        self.telegram(
                            f"🔒 <b>{symbol} TP2 → SL=TP1</b>\n"
                            f"📊 Fiyat: {current_price:.4f}\n"
                            f"🛡️ SL: {eski_sl:.4f} → {poz['sl']:.4f}"
                        )
                    self._kaydet()
                    continue
                
                if current_price >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    eski_sl = poz['sl']
                    poz['sl'] = poz['entry']
                    poz['tp1_tetiklendi'] = True
                    if self.telegram:
                        self.telegram(
                            f"🔒 <b>{symbol} TP1 → SL=Entry</b>\n"
                            f"📊 Fiyat: {current_price:.4f}\n"
                            f"🛡️ SL: {eski_sl:.4f} → {poz['sl']:.4f}\n"
                            f"✅ Risk sıfır!"
                        )
                    self._kaydet()
                    continue
                
                if current_price <= poz['sl']:
                    sebep = "BREAK-EVEN" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], sebep)
                    continue
            
            else:
                if current_price <= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3")
                    continue
                
                if current_price <= poz['tp2'] and not poz['tp2_tetiklendi']:
                    eski_sl = poz['sl']
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    if self.telegram:
                        self.telegram(
                            f"🔒 <b>{symbol} TP2 → SL=TP1</b>\n"
                            f"📊 Fiyat: {current_price:.4f}\n"
                            f"🛡️ SL: {eski_sl:.4f} → {poz['sl']:.4f}"
                        )
                    self._kaydet()
                    continue
                
                if current_price <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    eski_sl = poz['sl']
                    poz['sl'] = poz['entry']
                    poz['tp1_tetiklendi'] = True
                    if self.telegram:
                        self.telegram(
                            f"🔒 <b>{symbol} TP1 → SL=Entry</b>\n"
                            f"📊 Fiyat: {current_price:.4f}\n"
                            f"🛡️ SL: {eski_sl:.4f} → {poz['sl']:.4f}\n"
                            f"✅ Risk sıfır!"
                        )
                    self._kaydet()
                    continue
                
                if current_price >= poz['sl']:
                    sebep = "BREAK-EVEN" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], sebep)
                    continue
    
    def _slippage_uygula(self, fiyat, direction):
        if direction == "LONG":
            return fiyat * (1 + config.SLIPPAGE)
        else:
            return fiyat * (1 - config.SLIPPAGE)
    
    def pozisyon_kapat(self, poz, exit_price, yuzde, sebep):
        direction = poz['direction']
        entry = poz['entry']
        miktar = poz['miktar'] * (yuzde / 100)
        
        entry = self._slippage_uygula(entry, direction)
        exit_price = self._slippage_uygula(exit_price, "LONG" if direction == "SHORT" else "SHORT")
        
        if direction == "LONG":
            pnl = (exit_price - entry) / entry * miktar * config.KALDIRAC
        else:
            pnl = (entry - exit_price) / entry * miktar * config.KALDIRAC
        
        komisyon = miktar * config.KOMISYON * 2
        net_pnl = pnl - komisyon
        self.bakiye += miktar + net_pnl
        self.gunluk_gerceklesen_pnl += net_pnl
        self.peak_bakiye = max(self.peak_bakiye, self.bakiye)
        
        self.islem_gecmisi.append({
            'symbol': poz['symbol'],
            'direction': direction,
            'entry': entry,
            'exit': exit_price,
            'yuzde': yuzde,
            'sebep': sebep,
            'skor': poz.get('skor', 0),
            'pnl': net_pnl,
            'zaman': datetime.now().isoformat()
        })
        
        if sebep == "STOP" and poz['kalan_yuzde'] <= yuzde:
            self.cooldown_ekle(poz['symbol'], dakika=config.COOLDOWN_DAKIKA)
        
        if self.telegram:
            emoji = "✅" if net_pnl > 0 else "❌" if net_pnl < 0 else "⚖️"
            self.telegram(
                f"{emoji} <b>{poz['symbol']} {sebep}</b>\n\n"
                f"📊 Entry: {entry:.4f}\n"
                f"💰 Exit: {exit_price:.4f}\n"
                f"📈 PnL: ${net_pnl:+.2f}\n"
                f"🎯 %{yuzde} kapandı"
            )
        
        poz['kalan_yuzde'] -= yuzde
        if poz['kalan_yuzde'] <= 0:
            try:
                self.pozisyonlar.remove(poz)
            except:
                pass
        self._kaydet()
    
    def rapor(self):
        print("\n" + "=" * 60)
        print("📊 PAPER TRADE RAPORU")
        print("=" * 60)
        
        toplam = len(self.islem_gecmisi)
        kaz = sum(1 for i in self.islem_gecmisi if i['pnl'] > 0)
        kay = toplam - kaz
        pnl = sum(i['pnl'] for i in self.islem_gecmisi)
        
        efektif = self._efektif_bakiye_hesapla()
        dd = (self.peak_bakiye - efektif) / self.peak_bakiye * 100 if self.peak_bakiye > 0 else 0
        
        print(f"💰 Bakiye: ${self.bakiye:.2f}")
        print(f"💎 Efektif: ${efektif:.2f}")
        print(f"📈 Pozisyon: {len(self.pozisyonlar)}")
        print(f"📉 Drawdown: %{dd:.1f}")
        print(f"📊 İşlem: {toplam} (W:{kaz} L:{kay})")
        if toplam > 0:
            print(f"🎯 Win rate: %{kaz/toplam*100:.1f}")
        print(f"💵 PnL: ${pnl:+.2f}")
        print("=" * 60)