from flask import Flask, jsonify
from threading import Lock, Thread
import traceback
import sys

app = Flask(__name__)

# Global durum
bot_status = {
    "started": False,
    "error": None,
    "last_log": "Bekleniyor..."
}
_bot_thread = None
_bot_lock = Lock()

def run_bot():
    """Botu arka planda çalıştırır"""
    try:
        bot_status["last_log"] = "Bot import ediliyor..."
        import bot
        
        bot_status["last_log"] = "Bot başlatılıyor..."
        bot_status["started"] = True
        bot.main()
    except Exception as e:
        bot_status["started"] = False
        bot_status["error"] = str(e)
        bot_status["last_log"] = f"HATA: {e}"
        traceback.print_exc()
        sys.stdout.flush()


def start_bot():
    """Tek süreç içinde bot thread'ini yalnızca bir kez başlatır."""
    global _bot_thread
    with _bot_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            return False
        _bot_thread = Thread(target=run_bot, daemon=True, name="scalping-bot")
        _bot_thread.start()
        return True


@app.route('/')
def home():
    return f"Scalp Bot - Durum: {'ÇALIŞIYOR ✅' if bot_status['started'] else 'BEKLİYOR ⏳'}"

@app.route('/status')
def status():
    return jsonify({
        "bot_started": bot_status["started"],
        "error": bot_status["error"],
        "last_log": bot_status["last_log"]
    })

@app.route('/health')
def health():
    return "OK"

def run():
    start_bot()
    print("✅ Flask başlatıldı, port 10000")
    print("🤖 Bot thread'i başlatıldı")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    run()