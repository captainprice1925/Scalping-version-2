import json
import os
import tempfile

DOSYA = "scalp_bot_state.json"


def state_yukle():
    try:
        if os.path.exists(DOSYA):
            with open(DOSYA, "r", encoding="utf-8") as file:
                data = json.load(file)
                print(f"✅ Local state yüklendi (Bakiye: ${data.get('bakiye', 100):.2f})")
                return data
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"⚠ State okuma hatası: {error}")
    return None


def state_kaydet(state_dict):
    """State'i geçici dosyaya yazıp atomik olarak değiştirir.

    İşlem kesilirse eski dosya korunur; yarım JSON dosyasıyla yeniden başlama riski azalır.
    """
    directory = os.path.dirname(os.path.abspath(DOSYA))
    temp_path = None
    try:
        descriptor, temp_path = tempfile.mkstemp(
            prefix=".scalp_bot_state-", suffix=".tmp", dir=directory
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(state_dict, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, DOSYA)
    except (OSError, TypeError, ValueError) as error:
        print(f"⚠ State yazma hatası: {error}")
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
