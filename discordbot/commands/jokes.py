import discord
from discord import app_commands
import os
import random
import tempfile
import asyncio
from pathlib import Path
try:
    from ..tts_util import run_tts
    from ..audio_player import play_audio, get_voice_channel
    from ..history import log_command
    from ..reddit_loader import get_reddit_jokes
except ImportError:  # fallback when run as script from project root
    from tts_util import run_tts  # type: ignore
    from audio_player import play_audio, get_voice_channel  # type: ignore
    from history import log_command  # type: ignore
    from reddit_loader import get_reddit_jokes  # type: ignore

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "Audio"
audio_files = [f for f in os.listdir(AUDIO_DIR) if f.endswith(".mp3")] if AUDIO_DIR.exists() else []

async def setup(bot):
    @bot.tree.command(name="joke", description="Blague Reddit en vocal")
    @app_commands.describe(voice_channel="Salon vocal cible (optionnel)")
    async def joke(interaction: discord.Interaction, voice_channel: discord.VoiceChannel = None):
        await interaction.response.defer(thinking=True, ephemeral=True)  # Defer immediately
        log_command(interaction.user, "joke", {"voice_channel": str(voice_channel) if voice_channel else None}, guild=interaction.guild)
        reddit_jokes_by_sub = get_reddit_jokes()
        if not reddit_jokes_by_sub or not any(len(v) > 0 for v in reddit_jokes_by_sub.values()):
            await interaction.followup.send("Aucune blague pour le moment, réessaye plus tard.", ephemeral=True)
            return
        import math
        sub = random.choice([s for s in reddit_jokes_by_sub if reddit_jokes_by_sub[s]])
        posts = reddit_jokes_by_sub[sub]
        bias = 0.02
        weights = [math.exp(-bias * i) for i in range(len(posts))]
        idx = random.choices(range(len(posts)), weights=[w / sum(weights) for w in weights], k=1)[0]
        post = posts[idx]["data"]
        joke_text = f"{post['title']}. {post['selftext']}".strip()
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal, ou préciser un vocal !", ephemeral=True)
            return
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            filename = tmp.name
        loop = asyncio.get_running_loop()
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, joke_text, filename, "ash",
                                     "Read this joke with a comic tone, as if you are a stand-up comedian."),
                timeout=20
            )
            if not success:
                await interaction.followup.send("Erreur lors de la génération de la synthèse vocale.", ephemeral=True)
                return
            # Don't delete here — queue the playback.
            asyncio.create_task(play_audio(interaction, filename, vc_channel))
            await interaction.followup.send("Lecture audio lancée dans le salon vocal.", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"Erreur : {exc}", ephemeral=True)

    @bot.tree.command(name="jokeqc", description="Blague québécoise mp3")
    @app_commands.describe(voice_channel="Salon vocal cible (optionnel)")
    async def jokeqc(interaction: discord.Interaction, voice_channel: discord.VoiceChannel = None):
        log_command(interaction.user, "jokeqc", {"voice_channel": str(voice_channel) if voice_channel else None}, guild=interaction.guild)
        await interaction.response.defer(thinking=True, ephemeral=True)
        file = random.choice(audio_files)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal, ou préciser un vocal !", ephemeral=True)
            return
        try:
            asyncio.create_task(play_audio(interaction, os.path.join(str(AUDIO_DIR), file), vc_channel))
            await interaction.followup.send("Lecture audio lancée dans le salon vocal.", ephemeral=True)
        except Exception:
            await interaction.followup.send("Erreur pendant la lecture !", ephemeral=True)

    @bot.tree.command(name="penis", description="Joue un son spécial !")
    @app_commands.describe(voice_channel="Salon vocal cible (optionnel)")
    async def penis(interaction: discord.Interaction, voice_channel: discord.VoiceChannel = None):
        log_command(interaction.user, "penis", {"voice_channel": str(voice_channel) if voice_channel else None}, guild=interaction.guild)
        await interaction.response.defer(thinking=True, ephemeral=True)
        file = os.path.join(AUDIO_DIR, "sort-pas-ton-penis.mp3")
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal, ou préciser un vocal !", ephemeral=True)
            return
        try:
            asyncio.create_task(play_audio(interaction, file, vc_channel))
            await interaction.followup.send("Lecture audio lancée dans le salon vocal.", ephemeral=True)
        except Exception:
            await interaction.followup.send("Erreur pendant la lecture.", ephemeral=True)