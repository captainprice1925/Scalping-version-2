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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("✅ Telegram gönderildi")
    except Exception as e:
        print(f"⚠️ Telegram hatası: {e}")

def main():
    print("="*60)
    print("🚀 SCALP BOT BAŞLATILIYOR - V3 (Top10 - Skor4 - RR2.0 - OR)")
    print("="*60)

    pt = PaperTrade(telegram_func=send_telegram)

    send_telegram(f"🚀 <b>BOT V3 BAŞLATILDI</b>\n💰 Bakiye: ${pt.bakiye:.2f}\n📈 Pozisyon: {len(pt.pozisyonlar)}")

    while True:
        try:
            gun = datetime.now().weekday()
            gun_adi = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][gun]
            hafta_sonu = (gun >= 5)
            mod_adi = "🎉 HAFTA SONU (15m)" if hafta_sonu else "📅 HAFTA İÇİ (1h+4h OR)"

            print(f"\n🔍 Tarama: {datetime.now().strftime('%H:%M:%S')} - {gun_adi} - {mod_adi}")
            print("\n📊 BTC 4H çekiliyor...")
            btc_4h = veri_cek("BTCUSDT", config.TIMEFRAME_VETO, 500)
            if not btc_4h.empty:
                btc_4h = full_analysis(btc_4h)

            pt.gunluk_kontrol()

            for symbol in config.COINS:
                print(f"\n🔎 {symbol}...", end=" ")

                if hafta_sonu:
                    df_main = veri_cek(symbol, config.TIMEFRAME_MAIN_HAFTA_SONU, 500)
                    if df_main.empty:
                        print("❌ Veri yok"); continue
                    df_main = full_analysis(df_main)
                    # Hafta sonu: sadece 15m
                    sinyal, skor = sinyal_kontrol(df_main, None, None, symbol)
                    print(f"(15m)", end=" ")
                else:
                    df_1h = veri_cek(symbol, config.TIMEFRAME_MAIN_HAFTA_ICI, 500)
                    if df_1h.empty:
                        print("❌ 1H yok"); continue
                    df_4h = veri_cek(symbol, config.TIMEFRAME_MTF_HAFTA_ICI, 500)
                    if df_4h.empty:
                        print("❌ 4H yok"); continue
                    df_1h = full_analysis(df_1h)
                    df_4h = full_analysis(df_4h)
                    # Hafta içi: 1h OR 4h (OR mantığı)
                    sinyal, skor = sinyal_kontrol(None, df_1h, df_4h, symbol)
                    print(f"(1h+4h)", end=" ")
                    df_main = df_1h # entry için 1h kullan

                if sinyal:
                    print(f"✅ {sinyal} sinyali (Skor: {skor}/5)!")
                    entry = df_main['close'].iloc[-1]
                    atr = df_main['atr'].iloc[-1]
                    pt.islem_ac(symbol, sinyal, entry, atr, skor, df=df_main)
                else:
                    print(f"⏳ Sinyal yok (Skor: {skor}/5)")

                current_price = df_main['close'].iloc[-1]
                pt.pozisyon_guncelle(symbol, current_price)
                time.sleep(0.5)

            pt.rapor()

            tarama_araligi = config.TARAMA_ARALIGI_HAFTA_SONU if hafta_sonu else config.TARAMA_ARALIGI_HAFTA_ICI
            print(f"\n{mod_adi}: {tarama_araligi} sn bekleniyor...")
            time.sleep(tarama_araligi)

        except KeyboardInterrupt:
            print("\n🛑 Bot durduruldu"); break
        except Exception as e:
            print(f"❌ Hata: {e}"); time.sleep(60)

if __name__ == "__main__":
    main()