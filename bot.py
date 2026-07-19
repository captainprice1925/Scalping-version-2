import os
import time
import requests
from datetime import datetime
import config
from veri_cekici import veri_cek
from faz1_engine import full_analysis
from faz2_sinyal import sinyal_kontrol
from paper_trade import PaperTrade

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram hatası: {e}")

def main():
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
    
    pt = PaperTrade(telegram_func=send_telegram)
    
    while True:
        try:
            print(f"\n🔍 Tarama: {datetime.now().strftime('%H:%M:%S')}")
            
            print("\n📊 BTC 4H çekiliyor...")
            btc_4h = veri_cek("BTCUSDT", config.TIMEFRAME_VETO, 500)
            if not btc_4h.empty:
                btc_4h = full_analysis(btc_4h)
            
            pt.gunluk_kontrol()
            
            for symbol in config.COINS:
                print(f"\n🔎 {symbol}...", end=" ")
                
                df_15m = veri_cek(symbol, config.TIMEFRAME_MAIN, 500)
                if df_15m.empty:
                    print("❌ Veri yok")
                    continue
                
                df_1h = veri_cek(symbol, config.TIMEFRAME_MTF, 500)
                if df_1h.empty:
                    print("❌ 1H veri yok")
                    continue
                
                df_15m = full_analysis(df_15m)
                df_1h = full_analysis(df_1h)
                
                sinyal = sinyal_kontrol(df_15m, df_1h, btc_4h)
                
                if sinyal:
                    print(f"✅ {sinyal} sinyali!")
                    entry = df_15m['close'].iloc[-1]
                    atr = df_15m['atr'].iloc[-1]
                    mrc_mid = df_15m['mrc_mid'].iloc[-1]  # KRİTİK FIX
                    basarili = pt.islem_ac(symbol, sinyal, entry, atr, mrc_mid)  # mrc_mid geçirildi
                else:
                    print("⏳ Sinyal yok")
                
                current_price = df_15m['close'].iloc[-1]
                pt.pozisyon_guncelle(symbol, current_price)
                
                time.sleep(0.2)
            
            pt.rapor()
            print(f"\n💤 {config.TARAMA_ARALIGI} saniye bekleniyor...")
            time.sleep(config.TARAMA_ARALIGI)
            
        except KeyboardInterrupt:
            print("\n🛑 Bot durduruldu")
            send_telegram("🛑 <b>SCALP BOT DURDURULDU</b>")
            pt.rapor()
            break
        except Exception as e:
            error_msg = f"❌ Hata: {e}"
            print(error_msg)
            send_telegram(f"⚠️ <b>BOT HATASI</b>\n\n<code>{error_msg}</code>")
            time.sleep(60)

if __name__ == "__main__":
    main()