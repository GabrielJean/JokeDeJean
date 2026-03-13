# Project Guidelines

## Code Style
- Target Python 3.9+ compatibility for source code (runtime also supports newer versions via Docker).
- Prefer package-safe imports in bot modules:
  - Use package-relative imports first.
  - Add a script-style `ImportError` fallback only when module execution requires it.
- Keep slash-command modules structured around `async def setup(bot)` and command registration in that setup.
- Follow existing async interaction flow for slash commands: defer early for non-trivial work, then respond via follow-up.
- Keep user-facing failures graceful (send an interaction message instead of exposing tracebacks).

## Architecture
- Main entrypoint: `discordbot/main.py` (starts bot from `discordbot/bot_instance.py`).
- Command system: `discordbot/commands/__init__.py` dynamically loads command modules from `ALL_MODULES` using profile selection.
- Profiles:
  - `main`: non-music feature set.
  - `musiconly`: music-focused modules plus essentials.
  - `all`: fallback set.
- Runtime boundaries:
  - `discordbot/audio_player.py` handles guild voice queues/playback.
  - `discordbot/history.py` persists command history in JSON.
  - `discordbot/gpt_util.py` handles xAI/Grok calls.
  - `discordbot/reddit_loader.py` fetches Reddit jokes on startup and periodic refresh.

## Build And Run
- Install dependencies: `pip install -r requirements.txt`
- Run one profile:
  - `COMMAND_PROFILE=main python -m discordbot.main`
  - `COMMAND_PROFILE=musiconly python -m discordbot.main`
- Run both profiles: `python -m discordbot.run_both`
- Docker default runtime starts dual profile launcher from `discordbot.run_both`.
- There is currently no formal automated test suite in this repository.

## Conventions
- Keep command loading deterministic:
  - Add new command module names to `ALL_MODULES`.
  - Update `PROFILE_MAP` deliberately when changing profile behavior.
- Logging and config conventions:
  - Token resolution priority is `DISCORD_TOKEN` -> profile token map -> legacy `token`.
  - Per-profile log files are written under `discordbot/data/`.
- Startup assumptions:
  - `discordbot/config.json` must exist and be valid JSON before bot startup.
  - Encrypted Ansible Vault config is not accepted directly at runtime.
- Prefer narrowly scoped instruction files for specialized areas. For Discord command-specific rules, also follow `.github/instructions/discordbot-commands.instructions.md`.
