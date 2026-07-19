import json
from datetime import datetime, timedelta
import config

class PaperTrade:
    def __init__(self, telegram_func=None):
        self.bakiye = config.BUTCE_SANAL
        self.pozisyonlar = []
        self.islem_gecmisi = []
        self.telegram = telegram_func
        self.cooldown = {}
        self.gun_baslangic_bakiye = config.BUTCE_SANAL
        self.gun_tarihi = datetime.now().date()
        self.gunluk_limit_asildi = False
    
    def gunluk_kontrol(self):
        """Gün değiştiyse sayaçları sıfırlar; limit aşıldıysa True döner"""
        bugun = datetime.now().date()
        
        if bugun != self.gun_tarihi:
            self.gun_tarihi = bugun
            self.gun_baslangic_bakiye = self.bakiye
            self.gunluk_limit_asildi = False
            print(f"📅 Yeni gün - günlük sayaç sıfırlandı (Bakiye: ${self.bakiye:.2f})")
        
        gunluk_kayip = self.gun_baslangic_bakiye - self.bakiye
        gunluk_limit = self.gun_baslangic_bakiye * config.GUNLUK_KAYIP_LIMITI
        
        if gunluk_kayip >= gunluk_limit:
            if not self.gunluk_limit_asildi:
                self.gunluk_limit_asildi = True
                if self.telegram:
                    self.telegram(
                        f"🛑 <b>GÜNLÜK KAYIP LİMİTİ AŞILDI</b>\n\n"
                        f"📉 Günlük kayıp: ${gunluk_kayip:.2f} (limit: ${gunluk_limit:.2f})\n"
                        f"🚫 Yeni işlem yok, mevcut pozisyonlar yönetilmeye devam edecek"
                    )
            return True
        return False
    
    def sl_tp_hesapla(self, entry, atr, direction, mrc_mid=None):
        """RR bug fix: TP3 artık MRC kanal ortasına dayalı"""
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
        # Günlük kayıp limiti kontrolü
        if self.gunluk_kontrol():
            return False
        
        # Cooldown kontrolü
        if self.cooldown_kontrol(symbol):
            return False
        
        # Aynı coin açık pozisyon kontrolü
        for poz in self.pozisyonlar:
            if poz['symbol'] == symbol:
                print(f"⚠️ {symbol} için zaten açık pozisyon var")
                return False
        
        # Toplam pozisyon sayısı kontrolü
        if len(self.pozisyonlar) >= config.MAX_POZISYON:
            return False
        
        # 🆕 Aynı yönde pozisyon sayısı kontrolü (Korelasyon risk yönetimi)
        ayni_yon_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == direction)
        if ayni_yon_sayisi >= config.MAX_AYNI_YON:
            print(f"⚠️ Aynı yönde max pozisyon ({config.MAX_AYNI_YON}) dolu - {direction}")
            return False
        
        # Bakiye kontrolü
        if self.bakiye < config.ISLEM_BASINA:
            return False
        
        levels = self.sl_tp_hesapla(entry, atr, direction, mrc_mid)
        
        # RR filtresi artık gerçekten çalışıyor!
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
            'miktar': config.ISLEM_BASINA,
            'acilis_zamani': datetime.now().isoformat(),
            'tp1_tetiklendi': False,
            'tp2_tetiklendi': False,
            'kalan_yuzde': 100
        }
        
        self.pozisyonlar.append(pozisyon)
        self.bakiye -= config.ISLEM_BASINA
        
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
        
        return True
    
    def pozisyon_guncelle(self, symbol, current_price):
        for poz in self.pozisyonlar[:]:
            if poz['symbol'] != symbol:
                continue
            
            direction = poz['direction']
            
            if direction == "LONG":
                if current_price >= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, 100, "TP3")
                    continue
                if current_price >= poz['tp2'] and not poz['tp2_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP2_KAPANMA, "TP2")
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    poz['kalan_yuzde'] -= config.TP2_KAPANMA
                    continue
                if current_price >= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * (1 + config.KOMISYON)
                    poz['tp1_tetiklendi'] = True
                    poz['kalan_yuzde'] -= config.TP1_KAPANMA
                    continue
                if current_price <= poz['sl']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "STOP")
                    continue
            
            elif direction == "SHORT":
                if current_price <= poz['tp3']:
                    self.pozisyon_kapat(poz, current_price, 100, "TP3")
                    continue
                if current_price <= poz['tp2'] and not poz['tp2_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP2_KAPANMA, "TP2")
                    poz['sl'] = poz['tp1']
                    poz['tp2_tetiklendi'] = True
                    poz['kalan_yuzde'] -= config.TP2_KAPANMA
                    continue
                if current_price <= poz['tp1'] and not poz['tp1_tetiklendi']:
                    self.pozisyon_kapat(poz, current_price, config.TP1_KAPANMA, "TP1")
                    poz['sl'] = poz['entry'] * (1 - config.KOMISYON)
                    poz['tp1_tetiklendi'] = True
                    poz['kalan_yuzde'] -= config.TP1_KAPANMA
                    continue
                if current_price >= poz['sl']:
                    self.pozisyon_kapat(poz, current_price, poz['kalan_yuzde'], "STOP")
                    continue
    
    def pozisyon_kapat(self, poz, exit_price, yuzde, sebep):
        direction = poz['direction']
        entry = poz['entry']
        miktar = poz['miktar'] * (yuzde / 100)
        
        if direction == "LONG":
            pnl = (exit_price - entry) / entry * miktar * config.KALDIRAC
        else:
            pnl = (entry - exit_price) / entry * miktar * config.KALDIRAC
        
        komisyon = miktar * config.KOMISYON * 2
        net_pnl = pnl - komisyon
        self.bakiye += miktar + net_pnl
        
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
        
        if sebep == "STOP" and yuzde == 100:
            self.cooldown_ekle(poz['symbol'], dakika=60)
        
        if self.telegram:
            self.telegram(
                f"🔒 <b>{poz['symbol']} {sebep}</b>\n\n"
                f"📊 Entry: {entry:.4f}\n"
                f"💰 Exit: {exit_price:.4f}\n"
                f"📈 PnL: ${net_pnl:+.2f}\n"
                f"🎯 Kapanan: %{yuzde}"
            )
        
        if yuzde == 100 or poz['kalan_yuzde'] <= 0:
            self.pozisyonlar.remove(poz)
    
    def rapor(self):
        print("\n" + "=" * 60)
        print("📊 PAPER TRADE RAPORU")
        print("=" * 60)
        
        toplam_islem = len(self.islem_gecmisi)
        kazanilan = sum(1 for i in self.islem_gecmisi if i['pnl'] > 0)
        kaybedilen = toplam_islem - kazanilan
        toplam_pnl = sum(i['pnl'] for i in self.islem_gecmisi)
        
        gunluk_kayip = self.gun_baslangic_bakiye - self.bakiye
        gunluk_limit = self.gun_baslangic_bakiye * config.GUNLUK_KAYIP_LIMITI
        
        # Yön dağılımı
        long_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == "LONG")
        short_sayisi = sum(1 for poz in self.pozisyonlar if poz['direction'] == "SHORT")
        
        print(f"💰 Bakiye: ${self.bakiye:.2f}")
        print(f"📈 Açık pozisyon: {len(self.pozisyonlar)} (LONG: {long_sayisi}, SHORT: {short_sayisi})")
        print(f"⏳ Cooldown'daki coin: {len(self.cooldown)}")
        print(f"📉 Bugünkü kayıp: ${gunluk_kayip:.2f} / ${gunluk_limit:.2f} limit")
        print(f"📊 Toplam işlem: {toplam_islem}")
        print(f"✅ Kazanılan: {kazanilan}")
        print(f"❌ Kaybedilen: {kaybedilen}")
        
        if toplam_islem > 0:
            win_rate = kazanilan / toplam_islem * 100
            print(f"🎯 Win rate: %{win_rate:.1f}")
        
        print(f"💵 Toplam PnL: ${toplam_pnl:+.2f}")
        print("=" * 60)