import os
import json
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")
GIST_FILENAME = "scalp_bot_state.json"
GIST_API = f"https://api.github.com/gists/{GIST_ID}"

def _headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def state_yukle():
    if not GITHUB_TOKEN or not GIST_ID:
        print("⚠️ GITHUB_TOKEN/GIST_ID yok, persistence kapalı")
        return None
    try:
        r = requests.get(GIST_API, headers=_headers(), timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Gist okuma hatası: {r.status_code}")
            return None
        content = r.json()["files"][GIST_FILENAME]["content"]
        return json.loads(content) if content.strip() else None
    except Exception as e:
        print(f"⚠️ Gist okuma hatası: {e}")
        return None

def state_kaydet(state_dict):
    if not GITHUB_TOKEN or not GIST_ID:
        return
    try:
        payload = {"files": {GIST_FILENAME: {"content": json.dumps(state_dict, indent=2)}}}
        r = requests.patch(GIST_API, headers=_headers(), json=payload, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ Gist yazma hatası: {r.status_code}")
    except Exception as e:
        print(f"⚠️ Gist yazma hatası: {e}")