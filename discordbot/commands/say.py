# commands/say.py
import discord
from discord import app_commands
try:
    from ..audio_player import get_voice_channel, play_audio
    from ..tts_util import run_tts
    from ..history import log_command
    from ..guild_settings import get_tts_instructions_for
except ImportError:  # script fallback
    from audio_player import get_voice_channel, play_audio  # type: ignore
    from tts_util import run_tts  # type: ignore
    from history import log_command  # type: ignore
    from guild_settings import get_tts_instructions_for  # type: ignore

class SayModal(discord.ui.Modal, title="Envoyer un message dans ce salon"):
    message = discord.ui.TextInput(
        label="Message à afficher",
        style=discord.TextStyle.paragraph,
        max_length=1800,
        min_length=5,
        required=True,
        placeholder="Tape ici ton message à poster..."
    )

    async def on_submit(self, interaction: discord.Interaction):
        content = self.message.value.strip()
        log_command(
            interaction.user, "say_tc",
            {"message": content},
            guild=interaction.guild
        )
        # Envoi du message dans le salon de la commande
        await interaction.channel.send(content)
        await interaction.response.send_message("✅ Message envoyé !", ephemeral=True)

async def setup(bot):
    @bot.tree.command(name="say-tc", description="Affiche le texte dans le salon texte (UI si aucun paramètre)")
    @app_commands.describe(
        message="Message à afficher (si vide, ouvre une fenêtre)"
    )
    async def say_tc(interaction: discord.Interaction, message: str = None):
        if not message or not message.strip():
            await interaction.response.send_modal(SayModal())
            return
        content = message.strip()
        log_command(
            interaction.user, "say_tc",
            {"message": content},
            guild=interaction.guild
        )
        await interaction.channel.send(content)
        await interaction.response.send_message("✅ Message envoyé !", ephemeral=True)
