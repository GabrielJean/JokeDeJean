"""Dynamic command module loader.

Supports TWO primary profiles plus a fallback:
    - main       : everything except music-related modules
    - musiconly  : only music / yt / suno + core utility & management commands
    - all        : internal fallback (loads all modules)

Environment variables:
    COMMAND_PROFILE=main|musiconly|all
    COMMAND_MODULES=comma,list,of,module,names   # overrides COMMAND_PROFILE

Each module inside this package must expose `async def setup(bot)`.
The loader imports them dynamically in a deterministic order and calls setup.

This file is package-safe: works when running either
    python -m discordbot.main
or
    python discordbot/main.py

If you add new command modules, append their base name to ALL_MODULES.
"""

from importlib import import_module
import os
import logging
from types import ModuleType
from typing import Iterable, List

# Explicit list for clarity / deterministic order.
ALL_MODULES: List[str] = [
    "jokes",
    "tts",
    "gpt",
    "music",
    "moderation",
    "say",
    "util",
    "help",
    "roast",
    "compliment",
    "yt",
    "bot_mention",
    "settings",
    "suno",
]

# Profiles -> subset of module names. Adjust as you like.
PROFILE_MAP = {
    # main -> everything EXCEPT music-related modules
    "main": [
        "jokes", "tts", "gpt", "moderation", "say", "util", "help", "roast", "compliment", "bot_mention", "settings"
    ],
    # musiconly -> ONLY music-related modules (plus help + util + settings + moderation for basic control)
    "musiconly": [
        "music", "yt", "suno", "util", "help", "settings", "moderation", "bot_mention"
    ],
    # Internal fallback
    "all": ALL_MODULES,
}


def _resolve_allowed_modules() -> List[str]:
    # Highest precedence: explicit allowlist
    raw = os.getenv("COMMAND_MODULES")
    if raw:
        mods = [m.strip() for m in raw.split(",") if m.strip()]
        return [m for m in mods if m in ALL_MODULES]
    profile = os.getenv("COMMAND_PROFILE", "all").lower()
    allowed = PROFILE_MAP.get(profile)
    if not allowed:
        logging.warning("Unknown COMMAND_PROFILE '%s' — falling back to all", profile)
        allowed = ALL_MODULES
    return allowed


async def setup_all_commands(bot, allowed: Iterable[str] | None = None) -> list[str]:
    """Import and call setup(bot) for each selected command module.

    Parameters
    ----------
    bot : commands.Bot
        The bot instance.
    allowed : iterable[str] | None
        Optional explicit list of module base names (without package prefix).
        If None, resolution uses env vars (COMMAND_MODULES / COMMAND_PROFILE).
    """
    selected = list(allowed) if allowed else _resolve_allowed_modules()
    # Preserve order defined in ALL_MODULES
    ordered = [m for m in ALL_MODULES if m in selected]
    logging.info("Loading command modules: %s", ", ".join(ordered))
    loaded: list[str] = []
    base_pkg = __name__  # e.g. 'discordbot.commands'
    for name in ordered:
        full_name = f"{base_pkg}.{name}"
        try:
            mod: ModuleType = import_module(full_name)
            if hasattr(mod, "setup"):
                await mod.setup(bot)
                loaded.append(name)
            else:
                logging.warning("Module %s has no setup(bot) function", full_name)
        except Exception as exc:
            logging.exception("Failed loading command module %s: %s", full_name, exc)
    logging.info("Command modules loaded successfully: %s", ", ".join(loaded))
    return loaded

__all__ = ["setup_all_commands", "ALL_MODULES", "PROFILE_MAP"]