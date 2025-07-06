# commands/say.py
import discord
from discord import app_commands
from history import log_command

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
    @bot.tree.command(name="say-tc", description="Affiche le texte dans le salon texte")
    async def say_tc(interaction: discord.Interaction):
        await interaction.response.send_modal(SayModal())