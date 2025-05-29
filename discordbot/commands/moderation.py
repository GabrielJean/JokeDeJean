import discord
from discord import app_commands
import time
from history import log_command

_vc_blocks = {}  # (guild_id, channel_id): {user_id: until_ts}

async def setup(bot):
    @bot.tree.command(name="bloque", description="Bloque le bot pour 2h de rejoindre ton vocal actuel")
    async def bloque(interaction: discord.Interaction):
        log_command(interaction.user, "bloque", {}, guild=interaction.guild)
        user = interaction.user
        if not user.voice or not user.voice.channel:
            await interaction.response.send_message(
                "Tu dois être dans un salon vocal pour bloquer le bot !", ephemeral=True)
            return
        guild = interaction.guild
        channel = user.voice.channel
        key = (guild.id, channel.id)
        if key not in _vc_blocks:
            _vc_blocks[key] = {}
        _vc_blocks[key][user.id] = time.time() + 2 * 3600
        await interaction.response.send_message(
            f"🔒 Le bot ne peux rejoindre **{channel.name}** pour toi pendant 2h. Refais `/bloque` pour prolonger.",
            ephemeral=True)

    @bot.tree.command(name="debloque", description="Enlève ton blocage dans le salon vocal")
    async def debloque(interaction: discord.Interaction):
        log_command(interaction.user, "debloque", {}, guild=interaction.guild)
        user = interaction.user
        if not user.voice or not user.voice.channel:
            await interaction.response.send_message(
                "Tu dois être dans un salon vocal pour débloquer ce salon !", ephemeral=True)
            return
        guild = interaction.guild
        channel = user.voice.channel
        key = (guild.id, channel.id)
        if key not in _vc_blocks:
            _vc_blocks[key] = {}
        if user.id in _vc_blocks[key]:
            del _vc_blocks[key][user.id]
            await interaction.response.send_message(
                f"✅ Le blocage dans **{channel.name}** est retiré. Le bot peut à nouveau venir.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Ce salon n’était pas bloqué par toi !", ephemeral=True)