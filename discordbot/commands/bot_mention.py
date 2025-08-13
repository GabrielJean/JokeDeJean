import discord
from discord.ext import commands
import asyncio
import logging
import json
import os
import re
from collections import defaultdict, deque

from gpt_util import run_gpt

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json'))
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

DEFAULT_BOT_SYSTEM_PROMPT = (
    "You are {bot_name}, a funny and friendly virtual friend in our private Discord server. "
    "Reply in the same language as the user's message (English or French), and feel free to mix both if the conversation does. "
    "Your main goal is to make people smile with clever, playful, and gently teasing remarks, but always be genuine and adapt to the mood of the conversation. "
    "If the moment calls for real conversation or support, be a good listener and reply appropriately, while keeping a light and friendly tone. "
    "Join in on in-jokes, refer to previous messages, and interact like a natural part of the friend group. "
    "Don’t be overly sarcastic or mean, and don’t try to force a joke into every message. "
    "Don't explain your jokes, don't introduce yourself, just reply naturally as a friend would. "
    "User messages may be prefixed with 'Name:'. Do not include your own name or any speaker label in your replies—just write the message itself."
)
bot_system_prompt = config.get("bot_system_prompt", DEFAULT_BOT_SYSTEM_PROMPT)

MAX_HISTORY = 15


class BotMentionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY))

    def strip_self_label(self, bot_display_name: str, text: str) -> str:
        # Remove leading "BotName:" or "BotName —" etc.
        pattern = rf"^\s*{re.escape(bot_display_name)}\s*[:\-–—]\s*"
        cleaned = re.sub(pattern, "", text or "").strip()
        return cleaned

    def make_gpt_history(self, history):
        """
        Convert stored (author, content, is_bot) tuples into chat messages.
        - User messages keep 'Author: content' so the model knows who is speaking.
        - Assistant messages are label-free to avoid the model copying its own name.
        """
        chat = []
        for (author, content, is_bot) in history:
            role = "assistant" if is_bot else "user"
            msg_content = content if is_bot else f"{author}: {content}"
            chat.append({"role": role, "content": msg_content})
        return chat

    def build_multimodal_messages(self, dynamic_system_prompt, history, current_author, current_text, current_images):
        # Build messages compatible with AzureOpenAI SDK chat.completions
        messages = [{"role": "system", "content": dynamic_system_prompt}]
        # Prior history: assistant entries are label-free; user entries keep "Name: ..."
        for (author, content, is_bot) in history:
            messages.append({
                "role": "assistant" if is_bot else "user",
                "content": content if is_bot else f"{author}: {content}"
            })
        # Current user message: include author label in text part so the model knows who's speaking
        if current_images:
            parts = []
            if current_text:
                parts.append({"type": "text", "text": f"{current_author}: {current_text}"})
            for url in current_images:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": url}
                })
            if parts:
                messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": f"{current_author}: {current_text}"})
        return messages

    async def get_personality_reply(self, channel, user_message, author_name, bot_display_name, image_urls=None):
        history = list(self.channel_histories[channel.id])

        # Dynamically format the prompt with the bot's display name
        base_system_prompt = bot_system_prompt.format(bot_name=bot_display_name)
        dynamic_system_prompt = (
            base_system_prompt
            + " Keep replies to 1–2 short sentences. Never include your own name or any speaker label in your messages; just write the message itself."
        )

        # If there are images, avoid duplicating the just-appended user text by removing it from history
        if image_urls:
            if history and not history[-1][2] and history[-1][0] == author_name and history[-1][1] == user_message:
                history = history[:-1]
            messages = self.build_multimodal_messages(
                dynamic_system_prompt,
                history,
                author_name,
                user_message,
                image_urls
            )
        else:
            messages = [{"role": "system", "content": dynamic_system_prompt}]
            messages += self.make_gpt_history(history)

        loop = asyncio.get_running_loop()
        try:
            # Use SDK path directly (run_gpt handles both list and string input)
            # Keep replies short for mentions: ~250 completion tokens
            reply = await asyncio.wait_for(
                loop.run_in_executor(None, run_gpt, messages, None, 250),
                timeout=30
            )
            reply = reply or "..."
            # Remove a leading "BotName:" if model still tries to add it
            reply = self.strip_self_label(bot_display_name, reply)
            return reply[:500]
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

            # Append current user message into history (so the model sees it for text-only)
            self.channel_histories[message.channel.id].append(
                (message.author.display_name, message.clean_content, False)
            )

            # Collect image attachment URLs if any
            image_urls = []
            for att in getattr(message, 'attachments', []) or []:
                if att.content_type and att.content_type.startswith('image/'):
                    image_urls.append(att.url)
                else:
                    # Fallback by extension
                    _, ext = os.path.splitext(att.filename or "")
                    if ext.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                        image_urls.append(att.url)

            reply_text = await self.get_personality_reply(
                message.channel,
                message.clean_content,
                message.author.display_name,
                bot_display_name,
                image_urls=image_urls
            )

            # Store assistant reply (label-free content)
            self.channel_histories[message.channel.id].append(
                (bot_display_name, reply_text, True)
            )

            # Classic style: actual Discord mention
            await message.channel.send(f"{message.author.mention} {reply_text}")


async def setup(bot):
    await bot.add_cog(BotMentionCog(bot))