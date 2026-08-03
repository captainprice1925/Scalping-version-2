import json
import os

DOSYA = "scalp_bot_state.json"

def state_yukle():
    try:
        if os.path.exists(DOSYA):
            with open(DOSYA, "r") as f:
                data = json.load(f)
                print(f"✅ Local state yüklendi (Bakiye: ${data.get('bakiye', 100):.2f})")
                return data
    except Exception as e:
        print(f"⚠ State okuma hatası: {e}")
    return None

def state_kaydet(state_dict):
    try:
        with open(DOSYA, "w") as f:
            json.dump(state_dict, f, indent=2)
    except Exception as e:
        print(f"⚠ State yazma hatası: {e}")
