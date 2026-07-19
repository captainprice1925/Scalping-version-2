import os
import time
import requests
from datetime import datetime
import config
from veri_cekici import veri_cek
from faz1_engine import full_analysis
from faz2_sinyal import sinyal_kontrol
from paper_trade import PaperTrade

# ═══════════════════════════════════════════════════
# 📱 TELEGRAM BİLDİRİM AYARLARI (Render Environment'dan okur)
# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    """Telegram'a mesaj gönderir"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram token/chat ID ayarlanmamış, bildirim atlanıyor")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram bildirimi gönderildi")
        else:
            print(f"❌ Telegram hatası: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Telegram bağlantı hatası: {e}")

# ═══════════════════════════════════════════════════
# 🚀 ANA FONKSİYON
# ═══════════════════════════════════════════════════
def main():
    # Bot başlangıç bildirimi
    send_telegram(
        "🚀 <b>SCALP BOT BAŞLATILDI</b>\n\n"
        f"💰 Bakiye: ${config.BUTCE_SANAL}\n"
        f"⚡ Kaldıraç: {config.KALDIRAC}x\n"
        f"🛡️ Max pozisyon: {config.MAX_POZISYON}\n"
        f"🎯 Coin sayısı: {len(config.COINS)}"
    )
    
    print("=" * 60)
    print("🚀 SCALP BOT BAŞLATILIYOR (Paper Trade)")
    print("=" * 60)
    print(f"💰 Sanal bakiye: ${config.BUTCE_SANAL}")
    print(f"🎯 İşlem başına: ${config.ISLEM_BASINA}")
    print(f"⚡ Kaldıraç: {config.KALDIRAC}x")
    print(f"🛡️ Max pozisyon: {config.MAX_POZISYON}")
    print("=" * 60)
    
    # Paper trade objesi - telegram fonksiyonunu parametre olarak geç
    pt = PaperTrade(telegram_func=send_telegram)
    
    # Ana döngü
    while True:
        try:
            print(f"\n🔍 Tarama: {datetime.now().strftime('%H:%M:%S')}")
            
            # 1. BTC 4H verisi çek (veto için)
            print("\n📊 BTC 4H çekiliyor...")
            btc_4h = veri_cek("BTCUSDT", config.TIMEFRAME_VETO, 500)
            if not btc_4h.empty:
                btc_4h = full_analysis(btc_4h)
            
            # 2. Her coin için tarama
            for symbol in config.COINS:
                print(f"\n🔎 {symbol}...", end=" ")
                
                # 15m veri
                df_15m = veri_cek(symbol, config.TIMEFRAME_MAIN, 500)
                if df_15m.empty:
                    print("❌ Veri yok")
                    continue
                
                # 1h veri
                df_1h = veri_cek(symbol, config.TIMEFRAME_MTF, 500)
                if df_1h.empty:
                    print("❌ 1H veri yok")
                    continue
                
                # İndikatör hesapla
                df_15m = full_analysis(df_15m)
                df_1h = full_analysis(df_1h)
                
                # Sinyal kontrolü
                sinyal = sinyal_kontrol(df_15m, df_1h, btc_4h)
                
                if sinyal:
                    print(f"✅ {sinyal} sinyali!")
                    
                    # İşlem aç
                    entry = df_15m['close'].iloc[-1]
                    atr = df_15m['atr'].iloc[-1]
                    
                    basarili = pt.islem_ac(symbol, sinyal, entry, atr)
                    if basarili:
                        print(f"   ✅ İşlem açıldı: {symbol} {sinyal}")
                else:
                    print("⏳ Sinyal yok")
                
                # Açık pozisyonları güncelle
                current_price = df_15m['close'].iloc[-1]
                pt.pozisyon_guncelle(symbol, current_price)
                
                time.sleep(0.2)
            
            # Rapor
            pt.rapor()
            
            print(f"\n💤 {config.TARAMA_ARALIGI} saniye bekleniyor...")
            time.sleep(config.TARAMA_ARALIGI)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Bot durduruldu")
            send_telegram("🛑 <b>SCALP BOT DURDURULDU</b>")
            pt.rapor()
            break
        except Exception as e:
            error_msg = f"❌ Hata: {e}"
            print(error_msg)
            send_telegram(f"⚠️ <b>BOT HATASI</b>\n\n<code>{error_msg}</code>")
            time.sleep(60)

# if __name__ == "__main__":
#     main()