import requests
"""TTS utility helper.

Uses the config accessor from bot_instance. Supports both package execution
(python -m discordbot.main) and direct script execution by providing a
relative-first then absolute import fallback for get_config.
"""
try:  # Package relative import (python -m discordbot.main)
    from .bot_instance import get_config  # type: ignore
except Exception:  # pragma: no cover - fallback when run as script
    try:
        from bot_instance import get_config  # type: ignore
    except Exception:  # Final fallback – define a stub to avoid crash
        def get_config():  # type: ignore
            return {}

def run_tts(joke_text, filename, voice, instructions):
    config = get_config() or {}
    try:
        resp = requests.post(
            config["tts_url"],
            headers={
                "api-key": config["api_key"],
                "Content-Type": "application/json"
            },
            json={
                "input": joke_text,
                "model": "gpt-4o-mini-tts",
                "voice": voice,
                "response_format": "mp3",
                "speed": 1.0,
                "instructions": instructions
            },
            timeout=15
        )
        if resp.status_code == 200:
            with open(filename, "wb") as f:
                f.write(resp.content)
            return True
        else:
            print(f"TTS error: {resp.status_code} {resp.text}")
            return False
    except Exception as ex:
        print(f"TTS network error: {ex}")
        return False