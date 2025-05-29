# commands/say.py
import discord
from discord import app_commands
from history import log_command

async def setup(bot):
    @bot.tree.command(name="say-tc", description="Affiche le texte dans le salon texte")
    @app_commands.describe(message="Texte à afficher")
    async def say_tc(interaction, message: str):
        log_command(
            interaction.user, "say_tc",
            {"message": message},
            guild=interaction.guild
        )
        await interaction.response.send_message(message)