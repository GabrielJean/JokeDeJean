from . import jokes, tts, gpt, moderation, say, util, help, roast, compliment, yt, bot_mention, settings

async def setup_all_commands(bot):
    await jokes.setup(bot)
    await tts.setup(bot)
    await gpt.setup(bot)
    await moderation.setup(bot)
    await say.setup(bot)
    await util.setup(bot)
    await help.setup(bot)
    await roast.setup(bot)
    await compliment.setup(bot)
    await yt.setup(bot)
    await bot_mention.setup(bot)   # <--- ADD THIS LINE
    await settings.setup(bot)
