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
            print(f"✅ Kayıtlı state yüklendi (Bakiye: ${self.bakiye:.2f}, {len(self.pozisyonlar)} açık pozisyon, {len(self.islem_gecmisi)} geçmiş işlem)")
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
    
    def gunluk_kontrol(self):
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
                        f"📉 Bugünkü gerçekleşen kayıp: ${gunluk_kayip:.2f} (limit: ${gunluk_limit:.2f})\n"
                        f"🚫 Yeni işlem yok, mevcut pozisyonlar yönetilmeye devam edecek"
                    )
                self._kaydet()
            return True
        return False
    
    def _max_drawdown_kontrol(self):
        """Peak bakiyeden %15 düşerse yeni işlem açılmaz - BUG FIX: sadece bir kez mesaj"""
        if self.bakiye < self.peak_bakiye * (1 - config.MAX_DRAWDOWN):
            # 🆕 Flag kontrolü - sadece bir kez mesaj gönder
            if not self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = True
                if self.telegram:
                    self.telegram(
                        f"⚠️ <b>MAX DRAWDOWN LİMİTİ AŞILDI</b>\n\n"
                        f"📉 Bakiye: ${self.bakiye:.2f} (Peak: ${self.peak_bakiye:.2f})\n"
                        f"🚫 Yeni işlem yok, mevcut pozisyonlar yönetilmeye devam edecek\n"
                        f"💡 Bakiye toparlanana kadar yeni işlem açılmayacak"
                    )
                self._kaydet()
            return True
        else:
            # Bakiye toparlandıysa flag'i resetle
            if self.drawdown_limit_asildi:
                self.drawdown_limit_asildi = False
                if self.telegram:
                    self.telegram(
                        f"✅ <b>DRAWDOWN TOPARLANDI</b>\n\n"
                        f"💰 Bakiye: ${self.bakiye:.2f} (Peak: ${self.peak_bakiye:.2f})\n"
                        f"🚀 Yeni işlemler tekrar aktif!"
                    )
                self._kaydet()
            return False
    
    def _adaptive_pozisyon_hesapla(self):
        adaptive_tutar = min(
            self.bakiye * config.POZISYON_ORANI,
            config.ISLEM_BASINA
        )
        return max(adaptive_tutar, config.MIN_ISLEM_TUTAR)
    
    def sl_tp_hesapla(self, entry, atr, direction, mrc_mid=None):
        one_r = atr * config.ATR_CARPI
        max_sl = entry * config.MAX_SL_YUZDE
        sl_mesafe = min(one_r, max_sl)
        
        if direction == "LONG":
            sl = entry - sl_mesafe
            if mrc_mid is not None and mrc_mid > entry:
                hedef_mesafe = mrc_mid - entry
            else:
                hedef_mesafe = sl_mesafe * config.TP3_CARPI
            tp1 = entry + hedef_mesafe * (config.TP1_CARPI / config.TP3_CARPI)
            tp2 = entry + hedef_mesafe * (config.TP2_CARPI / config.TP3_CARPI)
            tp3 = entry + hedef_mesafe
        else:
            sl = entry + sl_mesafe
            if mrc_mid is not None and mrc_mid < entry:
                hedef_mesafe = entry - mrc_mid
            else:
                hedef_mesafe = sl_mesafe * config.TP3_CARPI
            tp1 = entry - hedef_mesafe * (config.TP1_CARPI / config.TP3_CARPI)
            tp2 = entry - hedef_mesafe * (config.TP2_CARPI / config.TP3_CARPI)
            tp3 = entry - hedef_mesafe
        
        risk = abs(entry - sl)
        odul = abs(tp3 - entry)
        rr = odul / risk if risk > 0 else 0
        
        return {
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'rr': rr,
            'sl_mesafe': sl_mesafe
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
        print(f"⏳ {symbol} {dakika} dk cooldown'a alındı")
    
    def islem_ac(self, symbol, direction, entry, atr, mrc_mid=None):
        if self.gunluk_kontrol():
            return False
        
        if self._max_drawdown_kontrol():
            return False
        
        if self.cooldown_kontrol(symbol):
            return False
        
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol:
                print(f"⚠️ {symbol} için zaten açık pozisyon var")
                return False
        
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            return False
        
        ayni_yon_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == direction)
        if ayni_yon_sayisi >= config.MAX_AYNI_YON:
            print(f"⚠️ Aynı yönde max pozisyon ({config.MAX_AYNI_YON}) dolu - {direction}")
            return False
        
        if self.bakiye < config.MIN_ISLEM_TUTAR:
            return False
        
        adaptive_tutar = self._adaptive_pozisyon_hesapla()
        
        levels = self.sl_tp_hesapla(entry, atr, direction, mrc_mid)
        
        if levels['rr'] < config.MIN_RR:
            print(f"⚠️ {symbol} RR çok düşük: {levels['rr']:.2f} < {config.MIN_RR}")
            return False
        
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
                f"📊 Entry: {entry:.4f}\n"
                f"🛡️ SL: {levels['sl']:.4f}\n"
                f"🎯 TP1: {levels['tp1']:.4f}\n"
                f"🎯 TP2: {levels['tp2']:.4f}\n"
                f"🎯 TP3: {levels['tp3']:.4f}\n"
                f"📈 RR: {levels['rr']:.2f}"
            )
        
        self._kaydet()
        return True
    
    def pozisyon_guncelle(self, symbol, current_price):
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol:
                continue
            
            direction = poz['direction']
            pozisyon_degisti = False
            
            if direction == "LONG":
                if current_price >= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "TP3")
                    continue
                if current_price >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP2_KAPANMA, "TP2")
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    pozisyon_degisti = True
                    continue
                if current_price >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * (1 + config.KOMISYON)
                    poz['tp1_tetiklendi'] = True
                    pozisyon_degisti = True
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
                    pozisyon_degisti = True
                    continue
                if current_price <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * (1 - config.KOMISYON)
                    poz['tp1_tetiklendi'] = True
                    pozisyon_degisti = True
                    continue
                if current_price >= poz['sl']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "STOP")
                    continue
            
            if pozisyon_degisti:
                self._kaydet()
    
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
        
        islem = {
            'symbol': poz['symbol'],
            'direction': direction,
            'entry': entry,
            'exit': exit_price,
            'yuzde': yuzde,
            'sebep': sebep,
            'pnl': net_pnl,
            'zaman': datetime.now().isoformat()
        }
        self.islem_gecmisi.append(islem)
        
        if sebep == "STOP" and poz['kalan_yuzde'] <= yuzde:
            self.cooldown_ekle(poz['symbol'], dakika=60)
        
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
                print(f"✅ {poz['symbol']} pozisyonu listeden çıkarıldı")
            except ValueError:
                print(f"⚠️ {poz['symbol']} zaten listede yok")
        
        self._kaydet()
    
    def rapor(self):
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
        
        print(f"💰 Bakiye: ${self.bakiye:.2f}")
        print(f"📈 Açık pozisyon: {len(self.pozisyonlar)} (LONG: {long_sayisi}, SHORT: {short_sayisi})")
        print(f"⏳ Cooldown'daki coin: {len(self.cooldown)}")
        print(f"📉 Bugünkü gerçekleşen kayıp: ${gunluk_kayip:.2f} / ${gunluk_limit:.2f} limit")
        print(f"📉 Max drawdown limiti: ${self.peak_bakiye * config.MAX_DRAWDOWN:.2f} (Peak: ${self.peak_bakiye:.2f})")
        print(f"📊 Toplam işlem: {toplam_islem}")
        print(f"✅ Kazanılan: {kazanilan}")
        print(f"❌ Kaybedilen: {kaybedilen}")
        
        if toplam_islem > 0:
            win_rate = kazanilan / toplam_islem * 100
            print(f"🎯 Win rate: %{win_rate:.1f}")
        
        print(f"💵 Toplam PnL: ${toplam_pnl:+.2f}")
        print(f"🎯 Peak bakiye: ${self.peak_bakiye:.2f}")
        print("=" * 60)