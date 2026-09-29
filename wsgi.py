"""Gunicorn giriş noktası.

Procfile, botun yinelenmesini önlemek için yalnızca bir Gunicorn worker başlatmalıdır.
"""
import os

from app import app, start_bot  # noqa: F401 - Gunicorn bu modül adını kullanır.

if os.getenv("SCALPING_SKIP_BOT_START") != "1":
    start_bot()
