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
        """Günlük kayıp limiti kontrolü"""
        bugun = datetime.now().date()
        
        if bugun != self.gun_tarihi:
            self.gun_tarihi = bugun
            self.gunluk_gerceklesen_pnl = 0.0
            self.gunluk_limit_asildi = False
            print("📅 Yeni gün - günlük P&L sıfırlandı")
            self._kaydet()
        
        gunluk_limit = config.BUTCE_SANAL * config.GUNLUK_KAYIP_LIMITI
        gunluk_kayip = max(0, -self.gunluk_gerceklesen_pnl)
        
        if gunluk_kayip >= gunluk_limit:
            if not self.gunluk_limit_asildi:
                self.gunluk_limit_asildi = True
                if self.telegram:
                    self.telegram(
                        f"🛑 <b>GÜNLÜK KAYIP LİMİTİ AŞILDI</b>\n\n"
                        f"📉 Bugünkü kayıp: ${gunluk_kayip:.2f} (limit: ${gunluk_limit:.2f})\n"
                        f"🚫 Yeni işlem yok"
                    )
                self._kaydet()
            return True
        return False
    
    def _max_drawdown_kontrol(self):
        """Max drawdown kontrolü"""
        efektif_bakiye = self._efektif_bakiye_hesapla()
        
        if efektif_bakiye < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                if self.telegram:
                    self.telegram(
                        f"⚠️ <b>MAX DRAWDOWN LİMİTİ AŞILDI</b>\n\n"
                        f"💰 Efektif bakiye: ${efektif_bakiye:.2f} (Peak: ${self.peak_bakiye:.2f})\n"
                        f"🚫 Yeni işlem yok"
                    )
                self._kaydet()
            return True
        else:
            if self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = False
                if self.telegram:
                    self.telegram(
                        f"✅ <b>DRAWDOWN TOPARLANDI</b>\n\n"
                        f"💰 Efektif bakiye: ${efektif_bakiye:.2f}\n"
                        f"🚀 Yeni işlemler tekrar aktif!"
                    )
                self._kaydet()
            return False
    
    def _adaptive_pozisyon_hesapla(self):
        """Pozisyon boyutu hesapla (drawdown'a göre ayarla)"""
        efektif_bakiye = self._efektif_bakiye_hesapla()
        drawdown = (self.peak_bakiye - efektif_bakiye) / self.peak_bakiye
        
        # Normal pozisyon boyutu
        pozisyon_orani = config.POZISYON_ORANI
        
        # Drawdown %15'i geçtiyse pozisyon boyutunu yarıya düşür
        if drawdown >= config.DRAWDOWN_REDUCE:
            pozisyon_orani = config.POZISYON_ORANI / 2
            print(f"⚠️ Drawdown %{drawdown*100:.1f} - Pozisyon boyutu yarıya düştü")
        
        adaptive_tutar = min(
            efektif_bakiye * pozisyon_orani,
            config.BUTCE_SANAL * 0.1  # Max %10
        )
        
        return max(adaptive_tutar, config.MIN_ISLEM_TUTAR)
    
    def sl_tp_hesapla(self, entry, atr, direction):
        """SL/TP hesapla"""
        sl_mesafe = atr * config.ATR_CARPI_SL
        
        if direction == "LONG":
            sl = entry - sl_mesafe
            tp1 = entry + atr * config.TP1_CARPI
            tp2 = entry + atr * config.TP2_CARPI
            tp3 = entry + atr * config.TP3_CARPI
        else:
            sl = entry + sl_mesafe
            tp1 = entry - atr * config.TP1_CARPI
            tp2 = entry - atr * config.TP2_CARPI
            tp3 = entry - atr * config.TP3_CARPI
        
        risk = abs(entry - sl)
        odul = abs(tp3 - entry)
        rr = odul / risk if risk > 0 else 0
        
        return {
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'rr': rr
        }
    
    def cooldown_kontrol(self, symbol):
        if symbol not in self.cooldown:
            return False
        
        bitis = self.cooldown[symbol]
        if datetime.now() < bitis:
            kalan = (bitis - datetime.now()).seconds // 60
            print(f"⏳ {symbol} cooldown'da ({kalan} dk kaldı)")
            return True
        
        del self.cooldown[symbol]
        return False
    
    def cooldown_ekle(self, symbol, dakika=60):
        self.cooldown[symbol] = datetime.now() + timedelta(minutes=dakika)
    
    def islem_ac(self, symbol, direction, entry, atr, skor):
        """İşlem aç (risk yönetimi ile)"""
        # Risk kontrolleri
        if self.gunluk_kontrol():
            return False
        
        if self._max_drawdown_kontrol():
            return False
        
        if self.cooldown_kontrol(symbol):
            return False
        
        # Aynı coin'de pozisyon var mı?
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol:
                print(f"⚠️ {symbol} için zaten açık pozisyon var")
                return False
        
        # Max pozisyon kontrolü
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            print(f"⚠️ Max pozisyon ({config.MAX_POZISYON}) dolu")
            return False
        
        # Aynı yönde max pozisyon kontrolü
        ayni_yon_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == direction)
        if ayni_yon_sayisi >= config.MAX_AYNI_YON:
            print(f"⚠️ Aynı yönde max pozisyon ({config.MAX_AYNI_YON}) dolu")
            return False
        
        # Bakiye kontrolü
        if self.bakiye < config.MIN_ISLEM_TUTAR:
            print(f"⚠️ Yetersiz bakiye: ${self.bakiye:.2f}")
            return False
        
        # Pozisyon boyutu hesapla
        adaptive_tutar = self._adaptive_pozisyon_hesapla()
        
        # SL/TP hesapla
        levels = self.sl_tp_hesapla(entry, atr, direction)
        
        # Pozisyon oluştur
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
            'miktar': adaptive_tutar,
            'acilis_zamani': datetime.now().isoformat(),
            'tp1_tetiklendi': False,
            'tp2_tetiklendi': False,
            'kalan_yuzde': 100
        }
        
        self.pozisyonlar.append(pozisyon)
        self.bakiye -= adaptive_tutar
        
        if self.telegram:
            self.telegram(
                f"✅ <b>{symbol} {direction} AÇILDI</b>\n\n"
                f"🎯 Skor: {skor}/10\n"
                f"📊 Entry: {entry:.4f}\n"
                f"🛡️ SL: {levels['sl']:.4f}\n"
                f"🎯 TP1: {levels['tp1']:.4f}\n"
                f"🎯 TP2: {levels['tp2']:.4f}\n"
                f"🎯 TP3: {levels['tp3']:.4f}\n"
                f"📈 RR: {levels['rr']:.2f}\n"
                f"💰 Pozisyon: ${adaptive_tutar:.2f}"
            )
        
        self._kaydet()
        return True
    
    def pozisyon_guncelle(self, symbol, current_price):
        """Pozisyon güncelle (trailing stop)"""
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol:
                continue
            
            direction = poz['direction']
            
            if direction == "LONG":
                if current_price >= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3")
                    continue
                if current_price >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP2_KAPANMA, "TP2")
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    self._kaydet()
                    continue
                if current_price >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * 1.002  # Entry + %0.2 buffer
                    poz['tp1_tetiklendi'] = True
                    self._kaydet()
                    continue
                if current_price <= poz['sl']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "STOP")
                    continue
            
            elif direction == "SHORT":
                if current_price <= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3")
                    continue
                if current_price <= poz['tp2'] and not poz['tp2_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP2_KAPANMA, "TP2")
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    self._kaydet()
                    continue
                if current_price <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * 0.998  # Entry - %0.2 buffer
                    poz['tp1_tetiklendi'] = True
                    self._kaydet()
                    continue
                if current_price >= poz['sl']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "STOP")
                    continue
    
    def _slippage_uygula(self, fiyat, direction):
        if direction == "LONG":
            return fiyat * (1 + config.SLIPPAGE)
        else:
            return fiyat * (1 - config.SLIPPAGE)
    
    def pozisyon_kapat(self, poz, exit_price, yuzde, sebep):
        """Pozisyon kapat"""
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
        
        islem = {
            'symbol': poz['symbol'],
            'direction': direction,
            'entry': entry,
            'exit': exit_price,
            'yuzde': yuzde,
            'sebep': sebep,
            'skor': poz.get('skor', 0),
            'pnl': net_pnl,
            'zaman': datetime.now().isoformat()
        }
        self.islem_gecmisi.append(islem)
        
        if sebep == "STOP" and poz['kalan_yuzde'] <= yuzde:
            self.cooldown_ekle(poz['symbol'], dakika=config.COOLDOWN_DAKIKA)
        
        if self.telegram:
            self.telegram(
                f"🔒 <b>{poz['symbol']} {sebep}</b>\n\n"
                f"📊 Entry: {entry:.4f}\n"
                f"💰 Exit: {exit_price:.4f}\n"
                f"📈 PnL: ${net_pnl:+.2f}\n"
                f"🎯 Kapanan: %{yuzde} (Kalan: %{max(0, poz['kalan_yuzde'] - yuzde)})"
            )
        
        poz['kalan_yuzde'] -= yuzde
        
        if poz['kalan_yuzde'] <= 0:
            try:
                self.pozisyonlar.remove(poz)
            except ValueError:
                pass
        
        self._kaydet()
    
    def rapor(self):
        """Rapor yazdır"""
        print("\n" + "=" * 60)
        print("📊 PAPER TRADE RAPORU")
        print("=" * 60)
        
        toplam_islem = len(self.islem_gecmisi)
        kazanilan = sum(1 for i in self.islem_gecmisi if i['pnl'] > 0)
        kaybedilen = toplam_islem - kazanilan
        toplam_pnl = sum(i['pnl'] for i in self.islem_gecmisi)
        
        gunluk_kayip = max(0, -self.gunluk_gerceklesen_pnl)
        gunluk_limit = config.BUTCE_SANAL * config.GUNLUK_KAYIP_LIMITI
        
        long_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == "LONG")
        short_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == "SHORT")
        
        efektif_bakiye = self._efektif_bakiye_hesapla()
        pozisyondaki_para = efektif_bakiye - self.bakiye
        drawdown = (self.peak_bakiye - efektif_bakiye) / self.peak_bakiye * 100
        
        print(f"💰 Nakit bakiye: ${self.bakiye:.2f}")
        print(f"📊 Pozisyonlarda: ${pozisyondaki_para:.2f}")
        print(f"💎 Efektif bakiye: ${efektif_bakiye:.2f}")
        print(f"📈 Açık pozisyon: {len(self.pozisyonlar)} (LONG: {long_sayisi}, SHORT: {short_sayisi})")
        print(f"📉 Drawdown: %{drawdown:.1f}")
        print(f"📉 Günlük kayıp: ${gunluk_kayip:.2f} / ${gunluk_limit:.2f}")
        print(f"📊 Toplam işlem: {toplam_islem}")
        print(f"✅ Kazanılan: {kazanilan}")
        print(f"❌ Kaybedilen: {kaybedilen}")
        
        if toplam_islem > 0:
            win_rate = kazanilan / toplam_islem * 100
            print(f"🎯 Win rate: %{win_rate:.1f}")
        
        print(f"💵 Toplam PnL: ${toplam_pnl:+.2f}")
        print(f"🎯 Peak bakiye: ${self.peak_bakiye:.2f}")
        print("=" * 60)
