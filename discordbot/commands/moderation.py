import discord
from discord import app_commands
import time
try:
    from ..history import log_command
    from ..audio_player import _voice_audio_queues, _voice_now_playing
except ImportError:  # script fallback
    from history import log_command  # type: ignore
    from audio_player import _voice_audio_queues, _voice_now_playing  # type: ignore

# VC block dict: (guild_id, channel_id): {user_id: until_ts}
_vc_blocks = {}

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
        _vc_blocks.setdefault(key, {})[user.id] = time.time() + 2 * 3600
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

    @bot.tree.command(name="queue", description="Affiche la file d'attente vocale")
    async def queue(interaction: discord.Interaction):
        log_command(interaction.user, "queue", {}, guild=interaction.guild)
        guild = interaction.guild
        gid = guild.id if guild else 0
        description_lines = []

        # --- Now playing
        now = _voice_now_playing.get(gid)
        if now:
            title = now.get("title") or "Audio"
            url = now.get("url") or ""
            user = getattr(getattr(now.get("interaction"), "user", None), "display_name", None)
            if not user:
                user = getattr(getattr(now.get("interaction"), "user", None), "name", None)
            added_by = f"Ajouté par `{user}`" if user else "(inconnu·e)"
            cur_line = f"**En cours :** [{title}]({url}) {added_by}" if url else f"**En cours :** {title} {added_by}"
            description_lines.append(cur_line)

        # --- Queue
        q = _voice_audio_queues.get(gid)
        if q is None or q.empty():
            if not description_lines:
                await interaction.response.send_message("Aucune musique en attente dans la file.", ephemeral=True)
                return
        else:
            queue_items = []
            queue_data = list(q._queue)  # Direct access is OK for listing snapshots
            for ix, item in enumerate(queue_data):
                # Unpack as per your structure:
                # (file_path, fut, voice_channel, interaction, use_stream, duration, title, video_url, announce_message, loop, is_live, seek_pos, progress_msg, seek_view)
                file_path = item[0]
                interaction_added = item[3]
                title = (item[6] or "Audio")
                url = item[7]
                user = getattr(getattr(interaction_added, "user", None), "display_name", None)
                if not user:
                    user = getattr(getattr(interaction_added, "user", None), "name", None)
                added_by = f"par `{user}`" if user else "(Ajout par inconnu·e)"
                if url:
                    queue_items.append(f"{ix+1}. [{title}]({url}) {added_by}")
                else:
                    queue_items.append(f"{ix+1}. {title} {added_by}")
            description_lines.append("**File d'attente :**\n" + "\n".join(queue_items))

        embed = discord.Embed(
            title="🎶 File d'attente musicale",
            description="\n\n".join(description_lines),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)