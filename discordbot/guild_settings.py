import json
import os
import threading
from typing import Dict, Any, Optional

_DEFAULTS: Dict[str, Any] = {
    "tts_instructions": "Parle avec un accent québécois stéréotypé."
}

_LOCK = threading.Lock()
_STORE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'guild_settings.json'))

# In-memory cache
_cache: Dict[str, Dict[str, Any]] = {}

def _load() -> None:
    global _cache
    if not os.path.exists(_STORE_PATH):
        _cache = {}
        return
    try:
        with open(_STORE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                _cache = {str(k): dict(v) for k, v in data.items()}
            else:
                _cache = {}
    except Exception:
        _cache = {}


def _save() -> None:
    tmp_path = _STORE_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(_cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, _STORE_PATH)


def _merged_with_defaults(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(_DEFAULTS)
    if d:
        merged.update({k: v for k, v in d.items() if v is not None})
    return merged


def get_guild_settings(guild_id: int) -> Dict[str, Any]:
    with _LOCK:
        _load()
        return _merged_with_defaults(_cache.get(str(guild_id)))


def set_guild_setting(guild_id: int, key: str, value: Any) -> Dict[str, Any]:
    with _LOCK:
        _load()
        gid = str(guild_id)
        current = dict(_cache.get(gid) or {})
        current[key] = value
        _cache[gid] = current
        _save()
        return _merged_with_defaults(current)


def reset_guild_settings(guild_id: int) -> None:
    with _LOCK:
        _load()
        gid = str(guild_id)
        if gid in _cache:
            del _cache[gid]
            _save()


def get_tts_instructions(guild, fallback: Optional[str] = None) -> str:
    """Return the configured TTS instruction for a guild, or fallback/default."""
    try:
        gid = guild.id if guild else None
    except Exception:
        gid = None
    if gid is None:
        return fallback or _DEFAULTS["tts_instructions"]
    settings = get_guild_settings(gid)
    return settings.get("tts_instructions") or (fallback or _DEFAULTS["tts_instructions"])


def get_tts_instructions_for(guild, feature: str, fallback: Optional[str] = None) -> str:
    """
    Return TTS instructions for a specific feature, falling back to the guild global setting,
    then to the provided fallback, then to the hard default.
    feature in {"say_vc", "roast", "compliment"}
    """
    key_map = {
        "say_vc": "tts_say_vc",
        "roast": "tts_roast",
        "compliment": "tts_compliment",
    }
    feature_key = key_map.get(feature)
    try:
        gid = guild.id if guild else None
    except Exception:
        gid = None
    if gid is None:
        # No guild: return fallback or default
        return fallback or _DEFAULTS["tts_instructions"]
    settings = get_guild_settings(gid)
    if feature_key and settings.get(feature_key):
        return settings[feature_key]
    # Fallback to global
    if settings.get("tts_instructions"):
        return settings["tts_instructions"]
    return fallback or _DEFAULTS["tts_instructions"]


def clear_guild_setting(guild_id: int, key: str) -> None:
    """Remove a specific key from this guild's settings (soft reset of one field)."""
    with _LOCK:
        _load()
        gid = str(guild_id)
        cur = dict(_cache.get(gid) or {})
        if key in cur:
            del cur[key]
            if cur:
                _cache[gid] = cur
            else:
                _cache.pop(gid, None)
            _save()

