import discord
from discord.ext import commands
import asyncio
import logging
import json
import os
from collections import defaultdict, deque

from gpt_util import run_gpt

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json'))
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

DEFAULT_BOT_SYSTEM_PROMPT = (
    "You are {bot_name}, a humorous virtual friend in our private Discord server. "
    "Reply in the same language as the user's message (English or French), and feel free to mix both if the conversation does. "
    "Your main goal is to make people laugh with witty, clever, or gently sarcastic remarks. "
    "Be playful, tease people lightly, bounce off inside jokes, and never be mean-spirited. "
    "Respond as if you're just another friend in the group, and reference previous messages if possible. "
    "Don't explain your jokes, don't introduce yourself, just reply with your natural ‘friend banter’ tone."
)
bot_system_prompt = config.get("bot_system_prompt", DEFAULT_BOT_SYSTEM_PROMPT)
MAX_HISTORY = 15

class BotMentionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY))

    def make_gpt_history(self, history):
        chat = []
        for (author, content, is_bot) in history:
            chat.append({
                "role": "assistant" if is_bot else "user",
                "content": f"{author}: {content}"
            })
        return chat

    async def get_personality_reply(self, channel, user_message, author_name, bot_display_name):
        history = list(self.channel_histories[channel.id])
        history.append((author_name, user_message, False))
        # Dynamically format the prompt with the bot's display name
        dynamic_system_prompt = bot_system_prompt.format(bot_name=bot_display_name)
        messages = [{"role": "system", "content": dynamic_system_prompt}]
        messages += self.make_gpt_history(history)

        loop = asyncio.get_running_loop()
        try:
            try:
                reply = await asyncio.wait_for(
                    loop.run_in_executor(None, run_gpt, messages),
                    timeout=20
                )
            except TypeError:
                flat = "\n".join(
                    (msg["content"] for msg in messages[1:])
                ) + f"\n{author_name}: {user_message}\n{bot_display_name}:"
                reply = await asyncio.wait_for(
                    loop.run_in_executor(None, run_gpt, flat, dynamic_system_prompt),
                    timeout=20
                )
            return reply[:500] if reply else "..."
        except Exception as ex:
            logging.error(f"GPT error on mention reply: {ex}")
            return "Sorry, I had a brain freeze... Try again!"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if self.bot.user in message.mentions:
            # Get the current name or nickname of the bot in the context server
            if message.guild:
                me = message.guild.get_member(self.bot.user.id)
                bot_display_name = me.display_name if me else self.bot.user.display_name
            else:
                bot_display_name = self.bot.user.display_name

            self.channel_histories[message.channel.id].append(
                (message.author.display_name, message.clean_content, False)
            )

            reply_text = await self.get_personality_reply(
                message.channel,
                message.clean_content,
                message.author.display_name,
                bot_display_name
            )

            self.channel_histories[message.channel.id].append(
                (bot_display_name, reply_text, True)
            )

            # Classic style: actual Discord mention
            await message.channel.send(f"{message.author.mention} {reply_text}")

async def setup(bot):
    await bot.add_cog(BotMentionCog(bot))