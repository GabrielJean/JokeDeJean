import discord
from discord import app_commands
import tempfile
import asyncio
import yt_dlp
from audio_player import play_audio, get_voice_channel
from history import log_command

async def setup(bot):
    @bot.tree.command(
        name="yt",
        description="Joue l'audio d'une vidéo YouTube dans le vocal"
    )
    @app_commands.describe(
        url="Lien YouTube",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def yt(
        interaction: discord.Interaction,
        url: str,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "yt",
            {
                "url": url,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True, ephemeral=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        loop = asyncio.get_running_loop()
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            filename = tmp.name
        mp3_filename = filename.replace('.webm', '.mp3')
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': filename,
            'quiet': True,  # Normal log level
            'noplaylist': True,
            'ffmpeg_location': '/usr/bin',
            'overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        try:
            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            await asyncio.wait_for(loop.run_in_executor(None, download), timeout=60)
            import os
            if not os.path.exists(mp3_filename) or os.path.getsize(mp3_filename) == 0:
                await interaction.followup.send("Erreur: le fichier audio téléchargé est vide ou absent.", ephemeral=True)
                return
            asyncio.create_task(play_audio(interaction, mp3_filename, vc_channel))
            await interaction.followup.send("Lecture audio YouTube lancée dans le salon vocal.", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors du téléchargement ou de la lecture : {exc}", ephemeral=True)