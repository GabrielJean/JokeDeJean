# Jean the Québécois Bot
A Discord bot that tells jokes, roasts your friends, gives compliments, and reads it all out loud in a Québécois accent (GPT-4o TTS voice) — and manages a queue so you don’t miss anything even if several voice commands are sent in a row!
![Jean the Bot](https://emoji.gg/assets/emoji/8170-laugh-emoji.png)
## Main Features
- **Jokes from Reddit / Québécois jokes / special sound effects**
- **Fun slash commands**: `/joke`, `/jokeqc`, `/gpt`, `/roast`, `/compliment`, `/say-vc`, `/say-tc`, `/leave`, etc.
- **Smart voice reading**: the bot reads jokes and messages in the voice channel (GPT-4o TTS, configurable Québécois accent)
- **Customizable compliments and “roasts”**, with the option to provide facts/memes for more personalized jokes
- **Audio queue**: multiple readings can be scheduled and will play one after another, with no conflict even if several members send commands at the same time
- **Built-in /help** (lists all bot commands)
## Requirements
- Python 3.9 or higher
- **discord.py** ≥ 2.3
- The following Python modules: `discord`, `discord.ext`, `requests`
- A configuration file `config.json` in the format:
    ```json
    {
      "token": "YOUR_DISCORD_BOT_TOKEN_HERE",
      "tts_url": "TTS_API_URL",
      "azure_gpt_url": "GPT_API_URL",
      "api_key": "APIKEY_FOR_APIS"
    }
    ```
- A folder `./Audio` with MP3 files (for Québécois jokes and special sound effects)
## Installation
1. **Install the modules**
    ```
    pip install discord.py requests
    ```
2. **Create the `config.json` file** (see above)
3. **Add your MP3 sounds** to the folder `./Audio`
4. **Start the bot**
    ```
    python tonbot.py
    ```
## Main Commands
- `/help` – Shows all bot commands
- `/joke` – Plays a Reddit joke in voice
- `/jokeqc` – Plays a local Québécois joke (mp3)
- `/leave` – Forces the bot to leave the voice channel
- `/say-vc <text>` – Reads out text (configurable accent)
- `/say-tc <text>` – Writes text in the text channel
- `/gpt <question>` – Asks GPT-4o a question and reads the answer (voice/text)
- `/roast @member [intensity] [details]` – Fun public roast, Québécois accent (level 1 mild to 5 salty)
- `/compliment @member [details]` – Personalized and vocal compliment, Québécois accent
- `/reset-prompts` – Resets system prompts and TTS server configs
## How the Queue Works
When multiple members send audio commands (mp3/TTS reading), each request is placed in a queue and played **in order**.
👉 Nobody will be “cut off”: everything will be read in order without conflict.
## Bonus
- **Logs**: all bot activity is recorded in `bot.log`
- **Multi-server** compatible
- **Configurable accent** (with `/say-vc` or `/gpt`)
## Examples
```bash
/joke
/jokeqc
/roast @Martin 5 "Always late to games, loves pizzas"
/compliment @Julie "awesome at Mario Kart, best laugh on the server"
```