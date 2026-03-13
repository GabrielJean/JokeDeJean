# Jean the Discord Bot
A Discord bot that delivers jokes and roasts, and reads content aloud using TTS. It includes an audio queue to ensure voice outputs play sequentially.
![Jean the Bot](https://emoji.gg/assets/emoji/8170-laugh-emoji.png)

## Main Features
- **Reddit and local jokes**
- **Slash commands**: `/joke`, `/jokeqc`, `/roast`, `/say-vc`, `/say-tc`, `/leave`, and more
- **Voice playback**: reads jokes and messages in voice channels (configurable voice/accent)
- **Configurable prompts** for tailored humor
- **Audio queue** to serialize multiple voice requests
- **Built-in /help** to list available commands
## Two-Bot Mode (Exact Two Profiles)
Supports exactly TWO profiles — simple and minimal:

1. `main` – everything except music-related commands (`music`, `yt`, `suno`)
2. `musiconly` – only music-related commands plus essentials (`help`, `util`, `moderation`, `bot_mention`)

Configure both tokens directly in `config.json` (preferred — no shell exports needed):

```jsonc
{
    // Tokens map: the loader picks the entry matching COMMAND_PROFILE
    "tokens": {
        "main": "XXXX_MAIN_BOT_TOKEN",
        "musiconly": "YYYY_MUSIC_BOT_TOKEN"
    },
    // Optional single fallback token (unused if tokens map has the profile)
    "token": "(optional-fallback)",
    "xai_api_key": "XAI_API_KEY",
    "gpt_model": "grok-4-1-fast-non-reasoning",
    "tts_voice": "Leo",
    "tts_provider": "edge",
    "tts_default_instructions": "Accent parisien (français de Paris)",
    "tts_edge_voice": "fr-CA-AntoineNeural"
}
```

Run in two terminals (no env tokens required):

```bash
COMMAND_PROFILE=main python -m discordbot.main
COMMAND_PROFILE=musiconly python -m discordbot.main
```

Or use the dual launcher (see below) which spawns both automatically. If you ever want a custom subset of modules you can still set `COMMAND_MODULES="mod1,mod2"`, but normally you just pick the profile.

The `/help` command only shows commands loaded for that process.
### Run both profiles with one command
If you prefer not to open two terminals manually, use the bundled launcher:

```bash
python -m discordbot.run_both
# or
python discordbot/run_both.py
```

What it does:
* Spawns two child processes (`COMMAND_PROFILE=main` and `COMMAND_PROFILE=musiconly`).
* Prefixes each output line so you can distinguish them: `[main:OUT]`, `[musiconly:ERR]`, etc.
* Gracefully shuts both down on Ctrl+C (SIGINT) or SIGTERM.

Environment tips:
* You do not need to export `DISCORD_TOKEN`; the code resolves the active token from `config.json` based on `COMMAND_PROFILE`.
* Optional: setting `DISCORD_TOKEN` overrides the profile token for that process.

Future enhancements (easy to add later): auto-restart flags, health pings, unified structured JSON logs.

## Requirements
- Python 3.9 or higher
- **discord.py** ≥ 2.3
- `davey` (required by current discord.py voice backend)
- Python modules: `discord`, `discord.ext`, `requests`
- A configuration file `config.json` in the format:
    ```json
        {
            "token": "YOUR_DISCORD_BOT_TOKEN_HERE",
            "xai_api_key": "XAI_API_KEY",
            "gpt_model": "grok-4-1-fast-non-reasoning",
            "tts_voice": "Leo",
            "tts_provider": "edge",
            "tts_default_instructions": "Accent parisien (français de Paris)",
            "tts_edge_voice": "fr-CA-AntoineNeural"
        }
    ```
- A folder `./Audio` with MP3 files (for Québécois jokes and special sound effects)
## Installation
1. **Install dependencies**
    ```
    pip install -r requirements.txt
    ```
2. **Create `config.json`** (see above)
3. **Add MP3 assets** to `./Audio`
4. **Start the bot**
    ```
    python tonbot.py
    ```
    Or with module (recommended):
    ```bash
    DISCORD_TOKEN=xxxxx python -m discordbot.main
    ```
## Main Commands
- `/help` – Shows all bot commands
- `/joke` – Plays a Reddit joke in voice
- `/jokeqc` – Plays a local joke (mp3)
- `/leave` – Forces the bot to leave the voice channel
- `/say-vc <text>` – Reads out text (configurable voice/accent)
- `/say-tc <text>` – Writes text in the text channel
- `/roast @member [intensity] [details]` – Fun public roast (level 1 mild to 5 salty)
## How the Queue Works
When multiple members send audio commands (mp3/TTS reading), each request is placed in a queue and played **in order**.
This ensures each request is read without overlap or interruption.
## Notes
- **Logs**: bot activity is recorded in `bot.log`
- **Multi-server** compatible
- **Configurable voice/accent** via `/say-vc`
## Examples
```bash
/joke
/jokeqc
/roast @Martin 5 "Always late to games, loves pizzas"
```