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

def pozisyonlari_takip_et(pt):
    """Açık pozisyonları 1 dakıklık mumlarla bar-bar SL/TP kontrolü yapar."""
    for poz in pt.pozisyonlar[:]:
        symbol = poz['symbol']
        try:
            df_1m = veri_cek(symbol, config.POZISYON_TF, 15, sadece_kapali=False)
            if df_1m.empty:
                print(f"⚠️ {symbol}: 1m verisi alınamadı, SL/TP bu tur kontrol edilemedi")
                continue
            pt.pozisyon_bars_guncelle(symbol, df_1m)
        except Exception as e:
            print(f"⚠️ {symbol} pozisyon takip hatası: {e}")

def main():
    print("="*60)
    print("🚀 FATIH V5 - Kademeli TP + SL 1.5 ATR + 1m pozisyon takibi")
    print("="*60)
    pt = PaperTrade(telegram_func=send_telegram)
    send_telegram(f"🚀 <b>FATIH V5 BAŞLADI</b>\n💰 ${pt.bakiye:.2f}\n📋 Core: {config.COINS_CORE}")

    taranacak = get_taranacak_coinler()
    son_guncelleme = datetime.now()

    while True:
        try:
            # Önce açık pozisyonları takip et (her döngüde, 5 dk arayla)
            if pt.pozisyonlar:
                pozisyonlari_takip_et(pt)

            # Her 6 saatte dinamik listeyi güncelle
            if (datetime.now() - son_guncelleme).total_seconds() > 21600:
                taranacak = get_taranacak_coinler()
                son_guncelleme = datetime.now()

            print(f"\n🔍 Tarama {datetime.now().strftime('%H:%M:%S')} - {len(taranacak)} coin")
            pt.gunluk_kontrol()

            for symbol in taranacak:
                try:
                    print(f"\n🔎 {symbol}...", end=" ")
                    # Sinyal: son (henüz kapanmamış) 1H mumunu at - yarımlanmış mum sinyali bozmasın
                    df_1h = veri_cek(symbol, config.TIMEFRAME_GIRIS, 500, sadece_kapali=True)
                    if df_1h.empty: print("❌ 1H yok"); continue
                    df_4h = veri_cek(symbol, config.TIMEFRAME_TREND, 500, sadece_kapali=True)
                    if df_4h.empty: print("❌ 4H yok"); continue

                    df_1h = full_analysis(df_1h)
                    df_4h = full_analysis(df_4h)

                    sinyal, skor = sinyal_kontrol(None, df_1h, df_4h, symbol, df_4h=df_4h)

                    if sinyal:
                        print(f"✅ {sinyal} {skor}/4")
                        # Giriş canlı fiyattan: son 1m kapanışı
                        df_canli = veri_cek(symbol, config.POZISYON_TF, 2, sadece_kapali=False)
                        entry = df_canli['close'].iloc[-1] if not df_canli.empty else df_1h['close'].iloc[-1]
                        atr = df_1h['atr'].iloc[-1]
                        pt.islem_ac(symbol, sinyal, entry, atr, skor, df=df_1h)
                    else:
                        print(f"⏳ Yok {skor}/4")

                    time.sleep(0.3)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"❌ {symbol} hata: {e}")

            pt.rapor()
            print(f"\n⏳ {config.TARAMA_ARALIGI}sn bekleniyor...")
            time.sleep(config.TARAMA_ARALIGI)

        except KeyboardInterrupt:
            print("🛑 Durduruldu"); break
        except Exception as e:
            print(f"❌ Hata: {e}"); time.sleep(60)

if __name__ == "__main__":
    main()
