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
        print("⚠️ Telegram token/chat ID ayarlanmamış")
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
            print("✅ Telegram gönderildi")
        else:
            print(f"❌ Telegram HTTP hatası: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"⚠️ Telegram bağlantı hatası: {e}")

def main():
    print("=" * 60)
    print("🚀 SCALP BOT BAŞLATILIYOR (Paper Trade)")
    print("=" * 60)
    
    pt = PaperTrade(telegram_func=send_telegram)
    
    send_telegram(
        "🚀 <b>SCALP BOT BAŞLATILDI</b>\n\n"
        f"💰 Bakiye: ${pt.bakiye:.2f}\n"
        f"📊 Geçmiş işlem: {len(pt.islem_gecmisi)}\n"
        f"📈 Açık pozisyon: {len(pt.pozisyonlar)}\n"
        f"⚡ Kaldıraç: {config.KALDIRAC}x\n"
        f"🛡️ Max pozisyon: {config.MAX_POZISYON}\n"
        f"🎯 Coin sayısı: {len(config.COINS)}\n"
        f"📅 Mod: Hafta içi 1h+4h / Hafta sonu 15m"
    )
    
    while True:
        try:
            # 🆕 HAFTA İÇİ / HAFTA SONU KONTROLÜ
            gun = datetime.now().weekday()
            gun_adi = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][gun]
            hafta_sonu = (gun >= 5)
            
            if hafta_sonu:
                mod_adi = "🎉 HAFTA SONU (Scalp 15m)"
            else:
                mod_adi = "📅 HAFTA İÇİ (Swing 1h+4h)"
            
            print(f"\n🔍 Tarama: {datetime.now().strftime('%H:%M:%S')} - {gun_adi} - {mod_adi}")
            
            print("\n📊 BTC 4H çekiliyor...")
            btc_4h = veri_cek("BTCUSDT", config.TIMEFRAME_VETO, 500)
            if not btc_4h.empty:
                btc_4h = full_analysis(btc_4h)
            
            pt.gunluk_kontrol()
            
            for symbol in config.COINS:
                print(f"\n🔎 {symbol}...", end=" ")
                
                if hafta_sonu:
                    # 🎉 HAFTA SONU: Sadece 15m (scalp)
                    df_main = veri_cek(symbol, config.TIMEFRAME_MAIN_HAFTA_SONU, 500)
                    if df_main.empty:
                        print("❌ Veri yok")
                        continue
                    df_mtf = df_main  # MTF olarak aynı veriyi kullan
                    print(f"(15m)", end=" ")
                else:
                    # 📅 HAFTA İÇİ: 1h + 4h birlikte (multi-timeframe)
                    df_main = veri_cek(symbol, config.TIMEFRAME_MAIN_HAFTA_ICI, 500)
                    if df_main.empty:
                        print("❌ 1H veri yok")
                        continue
                    
                    df_mtf = veri_cek(symbol, config.TIMEFRAME_MTF_HAFTA_ICI, 500)
                    if df_mtf.empty:
                        print("❌ 4H veri yok")
                        continue
                    print(f"(1h+4h)", end=" ")
                
                # Analiz
                df_main = full_analysis(df_main)
                df_mtf = full_analysis(df_mtf)
                
                # Sinyal kontrol (df_main = haftaiçi 1h/haftasonu 15m, df_mtf = haftaiçi 4h/haftasonu 15m)
                sinyal, skor = sinyal_kontrol(df_main, df_mtf, btc_4h, symbol)
                
                if sinyal:
                    print(f"✅ {sinyal} sinyali (Skor: {skor}/10)!")
                    entry = df_main['close'].iloc[-1]
                    atr = df_main['atr'].iloc[-1]
                    basarili = pt.islem_ac(symbol, sinyal, entry, atr, skor, df=df_main)
                else:
                    print(f"⏳ Sinyal yok (Skor: {skor}/10)")
                
                # Pozisyon güncelle
                current_price = df_main['close'].iloc[-1]
                pt.pozisyon_guncelle(symbol, current_price)
                
                time.sleep(1.0)
            
            pt.rapor()
            
            # 🆕 TARAMA ARALIĞI (hafta içi/sonu)
            if hafta_sonu:
                tarama_araligi = config.TARAMA_ARALIGI_HAFTA_SONU
                print(f"\n🎉 HAFTA SONU ({gun_adi}): {tarama_araligi} saniye (15 dk) bekleniyor...")
            else:
                tarama_araligi = config.TARAMA_ARALIGI_HAFTA_ICI
                print(f"\n📅 HAFTA İÇİ ({gun_adi}): {tarama_araligi} saniye (1 saat) bekleniyor...")
            
            time.sleep(tarama_araligi)
            
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