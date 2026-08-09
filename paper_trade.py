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
            self._kaydet()
        gunluk_limit = config.BUTCE_SANAL * config.GUNLUK_KAYIP_LIMITI
        if max(0, -self.gunluk_gerceklesen_pnl) >= gunluk_limit:
            if not self.gunluk_limit_asildi:
                self.gunluk_limit_asildi = True
                self._kaydet()
            return True
        return False
    
    def _max_drawdown_kontrol(self):
        efektif = self._efektif_bakiye_hesapla()
        if efektif < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                self._kaydet()
            return True
        else:
            if self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = False
                self._kaydet()
            return False

    def akilli_sl_tp_hesapla(self, df, direction, atr):
        """FATIH V4 - SL 1.5 ATR / BE 0.6 ATR / TP 1.0 ATR"""
        row = df.iloc[-1]
        close = row['close']
        
        sl_atr = config.SL_ATR  # 1.5
        tp_atr = config.TP_ATR  # 1.0
        be_atr = config.BE_ATR  # 0.6
        
        if direction == "LONG":
            sl = close - atr * sl_atr
            tp1 = close + atr * be_atr      # 0.6 ATR -> BE'ye çek
            tp2 = close + atr * tp_atr * 0.7 # 0.7 ATR
            tp3 = close + atr * tp_atr       # 1.0 ATR final
        else:
            sl = close + atr * sl_atr
            tp1 = close - atr * be_atr
            tp2 = close - atr * tp_atr * 0.7
            tp3 = close - atr * tp_atr
        
        risk = abs(close - sl)
        odul = abs(tp3 - close)
        rr = odul / risk if risk > 0 else 0.66
        
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
            print(f"⛔ Günlük limit")
            return False
        if self._max_drawdown_kontrol(): 
            print(f"⛔ Max DD")
            return False
        if self.cooldown_kontrol(symbol): 
            print(f"⏳ {symbol} cooldown")
            return False
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol: 
                print(f"⏳ {symbol} zaten açık")
                return False
        if len(self.pozisyonlar) >= config.MAX_POZISYON: 
            print(f"⛔ Max pozisyon {config.MAX_POZISYON}")
            return False
        if self.bakiye < config.ISLEM_BASINA: 
            print(f"⛔ Bakiye yetersiz")
            return False
        
        levels = self.akilli_sl_tp_hesapla(df, direction, atr)
        
        pozisyon = {
            'symbol': symbol, 'direction': direction, 'entry': entry, 'atr': atr,
            'sl': levels['sl'], 'tp1': levels['tp1'], 'tp2': levels['tp2'], 'tp3': levels['tp3'],
            'rr': levels['rr'], 'skor': skor, 'miktar': config.ISLEM_BASINA,
            'acilis_zamani': datetime.now().isoformat(),
            'tp1_tetiklendi': False, 'tp2_tetiklendi': False, 'kalan_yuzde': 100
        }
        
        self.pozisyonlar.append(pozisyon)
        self.bakiye -= config.ISLEM_BASINA
        
        if self.telegram:
            self.telegram(
                f"✅ <b>{symbol} {direction}</b>\n"
                f"🎯 Skor: {skor}/4\n"
                f"💰 ${config.ISLEM_BASINA} x{config.KALDIRAC}\n"
                f"📊 Entry: {entry:.4f}\n"
                f"🛡 SL: {levels['sl']:.4f} (1.5 ATR)\n"
                f"🔒 BE: {levels['tp1']:.4f} (0.6 ATR)\n"
                f"🎯 TP: {levels['tp3']:.4f} (1.0 ATR)\n"
                f"📈 RR: {levels['rr']:.2f}"
            )
        self._kaydet()
        return True
    
    def pozisyon_guncelle(self, symbol, current_price):
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol: continue
            direction = poz['direction']
            if direction == "LONG":
                if current_price >= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3"); continue
                if current_price >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    poz['sl'] = poz['tp1']; poz['tp2_tetiklendi'] = True; self._kaydet(); continue
                if current_price >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True; self._kaydet(); continue
                if current_price <= poz['sl']:
                    sebep = "BE" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], sebep); continue
            else:
                if current_price <= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3"); continue
                if current_price <= poz['tp2'] and not poz['tp2_tetiklendi']:
                    poz['sl'] = poz['tp1']; poz['tp2_tetiklendi'] = True; self._kaydet(); continue
                if current_price <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    poz['sl'] = poz['entry']; poz['tp1_tetiklendi'] = True; self._kaydet(); continue
                if current_price >= poz['sl']:
                    sebep = "BE" if poz['tp1_tetiklendi'] else "STOP"
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], sebep); continue
    
    def _slippage_uygula(self, fiyat, direction):
        return fiyat * (1 + config.SLIPPAGE) if direction == "LONG" else fiyat * (1 - config.SLIPPAGE)
    
    def pozisyon_kapat(self, poz, exit_price, yuzde, sebep):
        direction = poz['direction']; entry = poz['entry']; miktar = poz['miktar'] * (yuzde / 100)
        entry = self._slippage_uygula(entry, direction)
        exit_price = self._slippage_uygula(exit_price, "LONG" if direction == "SHORT" else "SHORT")
        pnl = (exit_price - entry) / entry * miktar * config.KALDIRAC if direction == "LONG" else (entry - exit_price) / entry * miktar * config.KALDIRAC
        komisyon = miktar * config.KOMISYON * 2
        net_pnl = pnl - komisyon
        self.bakiye += miktar + net_pnl
        self.gunluk_gerceklesen_pnl += net_pnl
        self.peak_bakiye = max(self.peak_bakiye, self.bakiye)
        self.islem_gecmisi.append({'symbol': poz['symbol'], 'direction': direction, 'entry': entry, 'exit': exit_price, 'yuzde': yuzde, 'sebep': sebep, 'skor': poz.get('skor', 0), 'pnl': net_pnl, 'zaman': datetime.now().isoformat()})
        if sebep == "STOP" and poz['kalan_yuzde'] <= yuzde:
            self.cooldown_ekle(poz['symbol'], dakika=config.COOLDOWN_DAKIKA)
        if self.telegram:
            emoji = "✅" if net_pnl > 0 else "❌"
            self.telegram(f"{emoji} <b>{poz['symbol']} {sebep}</b>\n💰 Exit: {exit_price:.4f}\n📈 PnL: ${net_pnl:+.2f}")
        poz['kalan_yuzde'] -= yuzde
        if poz['kalan_yuzde'] <= 0:
            try: self.pozisyonlar.remove(poz)
            except: pass
        self._kaydet()
    
    def rapor(self):
        print("\n" + "="*60 + "\n📊 PAPER TRADE V4 RAPORU\n" + "="*60)
        toplam = len(self.islem_gecmisi); kaz = sum(1 for i in self.islem_gecmisi if i['pnl'] > 0); pnl = sum(i['pnl'] for i in self.islem_gecmisi)
        efektif = self._efektif_bakiye_hesapla(); dd = (self.peak_bakiye - efektif) / self.peak_bakiye * 100 if self.peak_bakiye > 0 else 0
        print(f"💰 Bakiye: ${self.bakiye:.2f}\n💎 Efektif: ${efektif:.2f}\n📈 Pozisyon: {len(self.pozisyonlar)}\n📉 Drawdown: %{dd:.1f}\n📊 İşlem: {toplam} (W:{kaz} L:{toplam-kaz})")
        if toplam > 0: print(f"🎯 Win rate: %{kaz/toplam*100:.1f}")
        print(f"💵 PnL: ${pnl:+.2f}\n" + "="*60)