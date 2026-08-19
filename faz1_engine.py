import pandas as pd
import numpy as np
import ccxt
import config

FALLBACK_COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","ADAUSDT","WLDUSDT","ZECUSDT","TUTUSDT","BNBUSDT"]

def get_exchange():
    if not hasattr(ccxt, 'weex'):
        raise RuntimeError("ccxt.weex yok - requirements.txt'teki ccxt sürümünü güncelleyin (>= 4.5)")
    return ccxt.weex({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def calc_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta>0,0).ewm(alpha=1/period).mean()
    loss = (-delta.where(delta<0,0)).ewm(alpha=1/period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calc_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    # Wilder yumuşatması (RSI ile aynı yöntem, standart ATR)
    df['atr'] = tr.ewm(alpha=1/period, min_periods=period).mean()
    df['atr_pct'] = df['atr'] / df['close'] * 100
    return df

def calc_ema(df):
    df['ema_21'] = df['close'].ewm(span=21).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    return df

def calc_volume(df):
    df['volume_ma20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma20']
    return df

def full_analysis(df):
    if df is None or len(df) < 210:
        return df
    df = calc_rsi(df)
    df = calc_atr(df)
    df = calc_ema(df)
    df = calc_volume(df)
    return df

SITE_KATEGORI = {
"1000BONKUSDT":"Meme","1000FLOKIUSDT":"Meme","1000PEPEUSDT":"Meme","1000SHIBUSDT":"Meme",
"AAVEUSDT":"DeFi","ADAUSDT":"Layer 1","AEROUSDT":"DeFi","AGLDUSDT":"GameFi","AMZNUSDT":"Hisse ve Emtia",
"APEUSDT":"GameFi","APTUSDT":"Layer 1","ARBUSDT":"Layer 2","ARKMUSDT":"AI","ARUSDT":"Infra","ATOMUSDT":"Layer 1",
"AVAXUSDT":"Layer 1","AXSUSDT":"GameFi","BANDUSDT":"Infra","BANKUSDT":"DeFi","BCHUSDT":"Layer 1","BERAUSDT":"Layer 1",
"BLURUSDT":"Infra","BNBUSDT":"Layer 1","BRETTUSDT":"Meme","BTCUSDT":"Layer 1","BZUSDT":"Hisse ve Emtia","CAKEUSDT":"DeFi",
"CELOUSDT":"Layer 1","CHZUSDT":"GameFi","CLUSDT":"Hisse ve Emtia","COMPUSDT":"DeFi","COWUSDT":"DeFi","CRVUSDT":"DeFi",
"CVXUSDT":"DeFi","DASHUSDT":"Layer 1","DOGEUSDT":"Meme","DOTUSDT":"Layer 1","DRIFTUSDT":"DeFi","DSYNCUSDT":"AI",
"DUSKUSDT":"Infra","DYDXUSDT":"DeFi","DYMUSDT":"Layer 2","EIGENUSDT":"DeFi","ENAUSDT":"DeFi","ENSUSDT":"Infra",
"ETCUSDT":"Layer 1","ETHFIUSDT":"DeFi","ETHUSDT":"Layer 1","EVAAUSDT":"DeFi","FARTCOINUSDT":"Meme","FETUSDT":"AI",
"FILUSDT":"Infra","FUTUUSDT":"Hisse ve Emtia","GMXUSDT":"DeFi","GRASSUSDT":"AI","HBARUSDT":"Layer 1","HYPEUSDT":"Layer 2",
"ICPUSDT":"Layer 1","IMXUSDT":"GameFi","INJUSDT":"DeFi","INTCUSDT":"Hisse ve Emtia","JASMYUSDT":"Infra","JELLYJELLYUSDT":"Meme",
"JTOUSDT":"DeFi","JUPUSDT":"DeFi","KAITOUSDT":"AI","KASUSDT":"Layer 1","LABUSDT":"DeFi","LDOUSDT":"DeFi","LINEAUSDT":"Layer 2",
"LINKUSDT":"Infra","LTCUSDT":"Layer 1","LYNUSDT":"DeFi","MANTAUSDT":"Layer 2","MINAUSDT":"Layer 1","MOODENGUSDT":"Meme",
"MORPHOUSDT":"DeFi","MOVEUSDT":"Layer 2","MUUSDT":"Hisse ve Emtia","NEARUSDT":"Layer 1","NEOUSDT":"Layer 1","NVDAUSDT":"Hisse ve Emtia",
"ONDOUSDT":"RWA","OPUSDT":"Layer 2","ORDIUSDT":"Infra","PAXGUSDT":"RWA","PENDLEUSDT":"DeFi","PENGUUSDT":"GameFi","PNUTUSDT":"Meme",
"POLUSDT":"Layer 2","POPCATUSDT":"Meme","PUMPUSDT":"Meme","PYTHUSDT":"Infra","QNTUSDT":"Infra","RENDERUSDT":"AI","RUNEUSDT":"DeFi",
"SANDUSDT":"GameFi","SEIUSDT":"Layer 1","SKHYNIXUSDT":"Hisse ve Emtia","SNDKUSDT":"Hisse ve Emtia","SOLUSDT":"Layer 1","SPCXUSDT":"Hisse ve Emtia",
"SPXUSDT":"Meme","SSVUSDT":"DeFi","STRKUSDT":"Layer 2","SUIUSDT":"Layer 1","TAOUSDT":"AI","THETAUSDT":"Layer 1","TIAUSDT":"Infra",
"TONUSDT":"Layer 1","TRBUSDT":"Infra","TRUMPUSDT":"Meme","TRXUSDT":"Layer 1","TSLAUSDT":"Hisse ve Emtia","TURBOUSDT":"Meme","TUTUSDT":"Meme",
"UNIUSDT":"DeFi","VETUSDT":"Layer 1","VIRTUALUSDT":"AI","WIFUSDT":"Meme","WLDUSDT":"AI","XAGUSDT":"RWA","XAUTUSDT":"RWA","XLMUSDT":"Layer 1",
"XMRUSDT":"Layer 1","XRPUSDT":"Layer 1","XTZUSDT":"Layer 1","YFIUSDT":"DeFi","YGGUSDT":"GameFi","ZECUSDT":"Layer 1","ZENUSDT":"Layer 1",
"ZKUSDT":"Layer 2","ZROUSDT":"Layer 2"
}

def get_dinamik_coins(exchange):
    try:
        tickers = exchange.fetch_tickers()
        clean_map = {}
        for sym, t in tickers.items():
            if "USDT" not in sym: continue
            base = sym.split('/')[0]
            clean = base + "USDT"
            clean_map[clean] = t

        adaylar = []
        for site_coin, kategori in SITE_KATEGORI.items():
            if kategori == "Hisse ve Emtia": continue
            if "XAU" in site_coin or "XAG" in site_coin: continue
            t = clean_map.get(site_coin)
            if not t: continue
            qv = t.get('quoteVolume') or t.get('baseVolume') or 0
            if qv < config.HACIM_MIN_USD: continue
            adaylar.append((site_coin, qv))

        adaylar.sort(key=lambda x: x[1], reverse=True)

        # WEEX fetch_tickers bid/ask döndürmez; spread kontrolü en yüksek hacimli
        # adaylarda emir defteri (order book) ile yapılır
        onayli = []
        for site_coin, _ in adaylar[:20]:
            if len(onayli) >= 12: break
            try:
                ob = exchange.fetch_order_book(f"{site_coin[:-4]}/USDT:USDT", 5)
                if not ob['bids'] or not ob['asks']: continue
                bid = ob['bids'][0][0]; ask = ob['asks'][0][0]
                if (ask - bid) / ask > config.SPREAD_MAX:
                    print(f"⛔ {site_coin} spread yüksek (%{(ask-bid)/ask*100:.3f}) atlandı")
                    continue
                onayli.append(site_coin)
            except Exception:
                continue

        print(f"🔍 WEEX FİLTRE: {len(adaylar)} aday -> {onayli}")
        return onayli if len(onayli) >= 5 else FALLBACK_COINS
    except Exception as e:
        print(f"⚠️ WEEX hata: {e}")
        return FALLBACK_COINS