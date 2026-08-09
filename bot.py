import os, time, requests
from datetime import datetime
import config
from veri_cekici import veri_cek, get_exchange
from faz1_engine import full_analysis, get_dinamik_coins
from faz2_sinyal import sinyal_kontrol
from paper_trade import PaperTrade

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram(m):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": m, "parse_mode": "HTML"}, timeout=10)
    except: pass

def get_taranacak_coinler():
    try:
        ex = get_exchange()
        dinamik = get_dinamik_coins(ex)
        coins = config.COINS_CORE[:]
        for c in dinamik:
            if c not in coins and len(coins) < config.COINS_MAX:
                coins.append(c)
        print(f"📋 Taranacak ({len(coins)}): {coins}")
        return coins
    except Exception as e:
        print(f"⚠️ Dinamik hatası {e}")
        return config.COINS_CORE

def main():
    print("="*60)
    print("🚀 FATIH V4 - Dinamik 5M$ + 4H EMA200 + 1H EMA21 + Vol1.3x")
    print("="*60)
    pt = PaperTrade(telegram_func=send_telegram)
    send_telegram(f"🚀 <b>FATIH V4 BAŞLADI</b>\n💰 ${pt.bakiye:.2f}\n📋 Core: {config.COINS_CORE}")

    taranacak = get_taranacak_coinler()
    son_guncelleme = datetime.now()

    while True:
        try:
            # Her 6 saatte dinamik listeyi güncelle
            if (datetime.now() - son_guncelleme).seconds > 21600:
                taranacak = get_taranacak_coinler()
                son_guncelleme = datetime.now()

            print(f"\n🔍 Tarama {datetime.now().strftime('%H:%M:%S')} - {len(taranacak)} coin")
            pt.gunluk_kontrol()

            for symbol in taranacak:
                print(f"\n🔎 {symbol}...", end=" ")
                df_1h = veri_cek(symbol, config.TIMEFRAME_GIRIS, 500)
                if df_1h.empty: print("❌ 1H yok"); continue
                df_4h = veri_cek(symbol, config.TIMEFRAME_TREND, 500)
                if df_4h.empty: print("❌ 4H yok"); continue

                df_1h = full_analysis(df_1h)
                df_4h = full_analysis(df_4h)

                sinyal, skor = sinyal_kontrol(None, df_1h, df_4h, symbol, df_4h=df_4h)

                if sinyal:
                    print(f"✅ {sinyal} {skor}/4")
                    entry = df_1h['close'].iloc[-1]
                    atr = df_1h['atr'].iloc[-1]
                    pt.islem_ac(symbol, sinyal, entry, atr, skor, df=df_1h)
                else:
                    print(f"⏳ Yok {skor}/4")

                # Pozisyon güncelle
                current = df_1h['close'].iloc[-1]
                pt.pozisyon_guncelle(symbol, current)
                time.sleep(0.3)

            pt.rapor()
            print(f"\n⏳ {config.TARAMA_ARALIGI}sn bekleniyor...")
            time.sleep(config.TARAMA_ARALIGI)

        except KeyboardInterrupt:
            print("🛑 Durduruldu"); break
        except Exception as e:
            print(f"❌ Hata: {e}"); time.sleep(60)

if __name__ == "__main__":
    main()