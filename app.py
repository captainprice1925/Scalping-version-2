from flask import Flask, jsonify
from threading import Thread
import traceback
import sys
import time

app = Flask(__name__)

# Global durum
bot_status = {
    "started": False,
    "error": None,
    "last_log": "Bekleniyor..."
}

def run_bot():
    """Botu arka planda çalıştırır"""
    try:
        bot_status["last_log"] = "Bot import ediliyor..."
        import bot
        
        bot_status["last_log"] = "Bot başlatılıyor..."
        bot_status["started"] = True
        bot.main()
    except Exception as e:
        bot_status["error"] = str(e)
        bot_status["last_log"] = f"HATA: {e}"
        traceback.print_exc()
        sys.stdout.flush()

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
    # Botu ayrı thread'de başlat
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("✅ Flask başlatıldı, port 10000")
    print("🤖 Bot thread'i başlatıldı")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    run()