import discord
from discord import app_commands
import tempfile
import asyncio
from tts_util import run_tts
from audio_player import play_audio, get_voice_channel
from history import log_command

async def setup(bot):
    @bot.tree.command(
        name="say-vc",
        description="Lecture TTS en vocal"
    )
    @app_commands.describe(
        message="Texte à lire",
        instructions="Style de la voix (optionnel)",
        sauvegarder_instructions="Réutiliser le style 24h",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def say_vc(
        interaction: discord.Interaction,
        message: str,
        instructions: str = None,
        sauvegarder_instructions: bool = False,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "say_vc",
            {
                "message": message,
                "instructions": instructions,
                "sauvegarder_instructions": sauvegarder_instructions,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        loop = asyncio.get_running_loop()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp: filename = tmp.name
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, message, filename, "ash", instructions or "Comic accent"),
                timeout=20
            )
            if not success:
                await interaction.followup.send("Erreur lors de la génération de la synthèse vocale.", ephemeral=True)
                return
            asyncio.create_task(play_audio(interaction, filename, vc_channel))
            await interaction.followup.send("Lecture TTS lancée.", ephemeral=False)
        except Exception as exc:
            await interaction.followup.send(f"Erreur : {exc}", ephemeral=True)