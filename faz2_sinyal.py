import config

def calculate_score_fatih(df_4h, df_1h):
    if df_4h is None or df_1h is None: return 0, None
    if len(df_4h) < 210 or len(df_1h) < 50: return 0, None

    last_4h = df_4h.iloc[-1]
    last_1h = df_1h.iloc[-1]

    if last_4h['ema_200']!= last_4h['ema_200'] or last_1h['ema_21']!= last_1h['ema_21']:
        return 0, None

    trend_long = last_4h['close'] > last_4h['ema_200']
    ema_dist = abs(last_1h['close'] - last_1h['ema_21']) / last_1h['close'] * 100
    vol_ok = last_1h['volume_ratio'] >= config.VOLUME_MULT

    score = 0
    yon = None

    if trend_long:
        if ema_dist < 0.8: score += 1
        if config.RSI_LONG_MIN <= last_1h['rsi'] <= config.RSI_LONG_MAX: score += 2
        if vol_ok: score += 1
        if score >= config.MIN_SKOR: yon = "LONG"
    else:
        if ema_dist < 0.8: score += 1
        if config.RSI_SHORT_MIN <= last_1h['rsi'] <= config.RSI_SHORT_MAX: score += 2
        if vol_ok: score += 1
        if score >= config.MIN_SKOR: yon = "SHORT"

    return score, yon

def sinyal_kontrol(df_15m, df_1h, btc_4h, symbol=None, df_4h=None):
    # Eski bot.py uyumu için df_4h parametresi
    if df_4h is None:
        df_4h = btc_4h
    skor, yon = calculate_score_fatih(df_4h, df_1h)
    if yon:
        print(f"✅ {symbol} Fatih {skor}/4 - {yon} RSI:{df_1h.iloc[-1]['rsi']:.1f} Vol:{df_1h.iloc[-1]['volume_ratio']:.1f}x")
        return yon, skor
    else:
        return None, skor