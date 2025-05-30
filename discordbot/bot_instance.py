import discord
from discord.ext import commands, tasks
import json
import logging
import os

with open("config.json", "r") as f:
    config = json.load(f)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("./data/bot.log"),
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

from reddit_loader import load_reddit_jokes

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

    if first_ready:
        logging.info("Loading Reddit jokes at startup...")
        await load_reddit_jokes()
        logging.info("Reddit jokes loaded.")
        refresh_reddit_jokes.start()
        first_ready = False

    from commands import setup_all_commands
    await setup_all_commands(bot)
    cmds = await bot.tree.sync()
    logging.info(f"Slash commands synced: {len(cmds)} cmds.")

    # Show normal status after all is ready
    await bot.change_presence(activity=discord.Game(name="Tape /help"))