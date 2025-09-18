import discord
from discord.ext import commands, tasks
import json
import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Always load config relative to this file so running with `python -m discordbot.main`
# from the project root still works.
config_path = BASE_DIR / "config.json"
with open(config_path, "r") as f:
    config = json.load(f)

# ---- Multi-token resolution ----
# Priority order:
# 1. DISCORD_TOKEN env var (explicit override)
# 2. COMMAND_PROFILE mapped token in config['tokens'] (if present)
# 3. Legacy single 'token' field in config.json
profile = os.getenv("COMMAND_PROFILE")
tokens_map = config.get("tokens") if isinstance(config.get("tokens"), dict) else {}
selected_token = None
if os.getenv("DISCORD_TOKEN"):
    selected_token = os.getenv("DISCORD_TOKEN")
elif profile and profile in tokens_map and tokens_map.get(profile):
    selected_token = tokens_map.get(profile)
else:
    selected_token = config.get("token", "")
config["token"] = selected_token

# API key override
config["api_key"] = os.getenv("AZURE_OPENAI_API_KEY", config.get("api_key", ""))

# Per-profile logging (so two processes don't fight over same file) — store under package data dir
profile_safe = (profile or "single").lower()
data_dir = BASE_DIR / "data"
data_dir.mkdir(parents=True, exist_ok=True)
log_path = data_dir / f"bot_{profile_safe}.log"
if not log_path.exists():
    log_path.touch()

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [%(levelname)s] [{profile_safe}] %(message)s",
    handlers=[
        logging.FileHandler(str(log_path)),
        logging.StreamHandler()
    ]
)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
def get_config():
    return config

try:
    from .reddit_loader import load_reddit_jokes
except ImportError:  # script style
    from reddit_loader import load_reddit_jokes  # type: ignore
import os

@tasks.loop(hours=24)
async def refresh_reddit_jokes():
    logging.info("Refreshing Reddit jokes (background)...")
    await load_reddit_jokes()
    logging.info("Reddit jokes refreshed.")

first_ready = True

@bot.event
async def on_ready():
    global first_ready
    logging.info(f"Bot logged in as {bot.user}!")

    # Show loading status immediately
    await bot.change_presence(activity=discord.Game(name="Loading..."))

    try:
        if first_ready:
            logging.info("Loading Reddit jokes at startup...")
            await load_reddit_jokes()
            logging.info("Reddit jokes loaded.")
            refresh_reddit_jokes.start()

            try:
                from .commands import setup_all_commands
            except ImportError:
                from commands import setup_all_commands  # type: ignore
            logging.info("Setting up command modules (first run)...")
            logging.info("Env COMMAND_MODULES=%s COMMAND_PROFILE=%s", os.getenv("COMMAND_MODULES"), os.getenv("COMMAND_PROFILE"))
            loaded = await setup_all_commands(bot)
            if not loaded:
                logging.error("No command modules loaded! Check import errors above or profile configuration.")
            logging.info("Syncing slash commands (first run)...")
            cmds = await bot.tree.sync()
            logging.info(f"Slash commands synced: {len(cmds)} cmds (expected ~{len(loaded)})")

            first_ready = False

        # Show normal status after all is ready — differentiate bots
        if profile_safe == "musiconly":
            status_text = "Musique: /help"
        elif profile_safe == "main":
            status_text = "Chat: /help"
        else:
            status_text = "Tape /help"
        await bot.change_presence(activity=discord.Game(name=status_text))
        logging.info("Bot status set to '%s'.", status_text)
    except Exception as e:
        logging.exception("Exception in on_ready")
        await bot.change_presence(activity=discord.Game(name="Erreur au démarrage"))