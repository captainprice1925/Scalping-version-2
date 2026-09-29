"""Telegram üzerinden salt-okunur durum komutları.

Bot yalnızca TELEGRAM_CHAT_ID ile eşleşen sohbetten gelen komutlara yanıt verir;
diğer sohbetler yok sayılır. Bu modül borsaya emir göndermez ve hesap durumunu
değiştirmez; yalnızca paper-trade durumunu raporlar.
"""

import time
from collections import deque
from datetime import datetime
from threading import Thread

import requests

import config

YARDIM_METNI = (
    "ℹ️ <b>Komutlar</b>\n"
    "/durum — açık pozisyonlar + hesap özeti\n"
    "/pozisyonlar — yalnızca pozisyonlar\n"
    "/hata — son hatalar ve sistem durumu\n"
    "/yardim — bu mesaj"
)

_hata_gecmisi = deque(maxlen=30)
_hata_toplam = 0
_baslangic = datetime.now()
_son_tarama = None
_son_tarama_sembol = None


def hata_ekle(kaynak, mesaj):
    """Son hata listesine zaman damgalı kayıt ekler (en fazla 30 kayıt tutulur)."""
    global _hata_toplam
    _hata_toplam += 1
    damga = datetime.now().strftime("%H:%M:%S")
    _hata_gecmisi.append(f"{damga} — {kaynak}: {mesaj}")


def son_tarama_guncelle(sembol_sayisi):
    global _son_tarama, _son_tarama_sembol
    _son_tarama = datetime.now()
    _son_tarama_sembol = sembol_sayisi


def _pozisyon_satirlari(pt):
    satirlar = []
    for pozisyon in list(pt.pozisyonlar):
        son = pozisyon.get("son_fiyat", pozisyon["entry"])
        acik_pnl = pt._brut_pnl(pozisyon, son) - pt._tahmini_cikis_komisyonu(pozisyon)
        risk = pt.tahmini_stop_riski(pozisyon)
        marjin = pt._kalan_marjin(pozisyon)
        satirlar.append(
            f"• <b>{pozisyon['symbol']} {pozisyon['direction']}</b> — kalan %{pozisyon['kalan_yuzde']:.0f}\n"
            f"  Giriş {pozisyon['giris_fiyat']:.6g} | Son {son:.6g}\n"
            f"  SL {pozisyon['sl']:.6g} | TP1 {pozisyon['tp1']:.6g} | "
            f"TP2 {pozisyon['tp2']:.6g} | TP3 {pozisyon['tp3']:.6g}\n"
            f"  PnL(tahmini) {acik_pnl:+.2f}$ | Stop riski {risk:.2f}$ | Marjin {marjin:.2f}$"
        )
    return satirlar


def ozet_mesaji(pt, sadece_pozisyon=False):
    baslik = "📌 POZİSYONLAR" if sadece_pozisyon else "📊 DURUM ÖZETİ"
    satirlar = [f"{baslik} — {datetime.now().strftime('%d.%m %H:%M:%S')}"]
    pozisyonlar = _pozisyon_satirlari(pt)
    if pozisyonlar:
        satirlar.append(f"📈 Açık pozisyon ({len(pozisyonlar)}/{config.MAX_POZISYON}):")
        satirlar.extend(pozisyonlar)
    else:
        satirlar.append("📭 Açık pozisyon yok.")
    if not sadece_pozisyon:
        efektif = pt._efektif_bakiye_hesapla()
        drawdown = (
            (pt.peak_bakiye - efektif) / pt.peak_bakiye * 100
            if pt.peak_bakiye > 0
            else 0
        )
        satirlar.append(
            f"💰 Nakit {pt.bakiye:.2f}$ | Efektif {efektif:.2f}$ | "
            f"Günlük PnL {pt.gunluk_gerceklesen_pnl:+.2f}$\n"
            f"📉 Drawdown %{drawdown:.1f} | Açık stop riski {pt._toplam_acik_risk():.2f}$"
        )
        aktif_cooldown = {
            sembol: bitis
            for sembol, bitis in pt.cooldown.items()
            if bitis > datetime.now()
        }
        if aktif_cooldown:
            parcalar = [
                f"{sembol} ({int((bitis - datetime.now()).total_seconds() // 60)}dk)"
                for sembol, bitis in aktif_cooldown.items()
            ]
            satirlar.append("⏱ Cooldown: " + ", ".join(parcalar))
        if _son_tarama is not None:
            gecen = int((datetime.now() - _son_tarama).total_seconds() // 60)
            satirlar.append(
                f"🔄 Son tarama {_son_tarama.strftime('%H:%M')} — "
                f"{_son_tarama_sembol} coin ({gecen} dk önce)"
            )
    return "\n".join(satirlar)


def hata_mesaji():
    simdi = datetime.now()
    satirlar = [
        "🩺 SİSTEM DURUMU",
        f"• Bot başlangıcı: {_baslangic.strftime('%d.%m %H:%M')} "
        f"({(simdi - _baslangic).total_seconds() / 3600:.1f} sa önce)",
    ]
    if _son_tarama is not None:
        satirlar.append(
            f"• Son tarama: {_son_tarama.strftime('%H:%M:%S')} — "
            f"{_son_tarama_sembol} coin "
            f"({int((simdi - _son_tarama).total_seconds() // 60)} dk önce)"
        )
    else:
        satirlar.append("• Son tarama: henüz yok")
    satirlar.append(f"• Toplam hata kaydı: {_hata_toplam}")
    if _hata_gecmisi:
        satirlar.append("⚠️ <b>Son hatalar:</b>")
        satirlar.extend(f"– {kayit}" for kayit in list(_hata_gecmisi)[-10:])
    else:
        satirlar.append("✅ Kayıtlı hata yok — sistem temiz görünüyor.")
    return "\n".join(satirlar)


def komut_isle(metin, pt):
    """Gelen metni komuta çevirir; bilinmeyen/ilgisiz mesajlarda None döner."""
    metin = (metin or "").strip().lower()
    if not metin.startswith("/"):
        return None
    komut = metin.split()[0].split("@")[0]
    if komut in ("/durum", "/ozet"):
        return ozet_mesaji(pt, sadece_pozisyon=False)
    if komut in ("/pozisyonlar", "/pozisyon"):
        return ozet_mesaji(pt, sadece_pozisyon=True)
    if komut in ("/hata", "/hatalar", "/saglik"):
        return hata_mesaji()
    if komut in ("/yardim", "/help", "/start"):
        return YARDIM_METNI
    return "🤔 Bilinmeyen komut. /yardim yazabilirsin."


def komut_dinleyici_baslat(pt, token, chat_id):
    """getUpdates döngüsünü ayrı bir daemon thread'de başlatır.

    Yalnızca chat_id ile eşleşen sohbetten gelen komutlar yanıtlanır; özellik
    salt-okunurdur (emir göndermez, hesap değiştirmez).
    """
    if not token or not chat_id:
        print("ℹ️ Telegram komut dinleyicisi kapalı (token/chat_id tanımlı değil)")
        return
    thread = Thread(
        target=_dinleme_dongusu,
        args=(pt, token, str(chat_id)),
        daemon=True,
        name="tg-komutlar",
    )
    thread.start()
    print("🛰 Telegram komut dinleyicisi başladı (/durum, /pozisyonlar, /hata, /yardim)")


def _dinleme_dongusu(pt, token, chat_id):
    offset = None
    while True:
        try:
            parametreler = {"timeout": 25, "allowed_updates": '["message"]'}
            if offset is not None:
                parametreler["offset"] = offset
            cevap = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params=parametreler,
                timeout=40,
            )
            veri = cevap.json()
            for guncelleme in veri.get("result", []):
                offset = guncelleme["update_id"] + 1
                mesaj = guncelleme.get("message") or {}
                sohbet_id = str((mesaj.get("chat") or {}).get("id", ""))
                if sohbet_id != chat_id:
                    continue
                try:
                    komut_cevabi = komut_isle(mesaj.get("text") or "", pt)
                except Exception as inner:
                    hata_ekle("komut işleme", inner)
                    komut_cevabi = (
                        "⚠️ Komut işlenirken hata oluştu; /hata ile son kayıtlara bakabilirsin."
                    )
                if komut_cevabi:
                    try:
                        requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": komut_cevabi,
                                "parse_mode": "HTML",
                            },
                            timeout=15,
                        )
                    except Exception as inner:
                        hata_ekle("telegram gönderim", inner)
            time.sleep(1)
        except Exception as error:
            hata_ekle("telegram dinleyici", error)
            time.sleep(5)
