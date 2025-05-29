import threading
import json
import os
from datetime import datetime

HISTORY_FILE = "./data/command_history.json"
_history_lock = threading.Lock()

def log_command(user, command_name, options, guild=None):
    entry = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "user_id": user.id,
        "user": str(user),
        "command": command_name,
        "params": options,
        "guild_id": guild.id if guild else None
    }
    with _history_lock:
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as src:
                    history = json.load(src)
            else:
                history = []
        except Exception:
            history = []
        history.append(entry)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as out:
                json.dump(history, out, ensure_ascii=False, indent=2)
        except Exception:
            pass

def get_recent_history(n=15):
    with _history_lock:
        try:
            if not os.path.exists(HISTORY_FILE):
                return []
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            return []
    return items[-n:] if len(items) > n else items