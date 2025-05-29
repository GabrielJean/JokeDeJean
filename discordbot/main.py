from bot_instance import bot, get_config
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot from main.py...")
    token = get_config()["token"]
    bot.run(token)