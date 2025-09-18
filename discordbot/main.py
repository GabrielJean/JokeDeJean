try:
    # When executed as a module: python -m discordbot.main
    from .bot_instance import bot, get_config  # type: ignore
except ImportError:  # When executed as a script: python discordbot/main.py
    from bot_instance import bot, get_config  # type: ignore
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot from main.py...")
    token = get_config()["token"]
    bot.run(token)