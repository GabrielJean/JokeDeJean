import discord
from discord import app_commands
from history import log_command, get_recent_history

async def setup(bot):
    @bot.tree.command(name="leave", description="Quitte le vocal")
    async def leave(interaction: discord.Interaction):
        log_command(interaction.user, "leave", {}, guild=interaction.guild)
        await interaction.response.defer(thinking=True, ephemeral=True)
        vc = None
        for client in bot.voice_clients:
            if client.guild == interaction.guild:
                vc = client
                break
        if vc:
            try: await vc.disconnect(force=True)
            except Exception:
                await interaction.followup.send("Erreur de déconnexion.", ephemeral=True)
            else:
                await interaction.followup.send("Je quitte le salon vocal.", ephemeral=True)
        else:
            await interaction.followup.send("Le bot n'est pas connecté au vocal.", ephemeral=True)

    @bot.tree.command(name="history", description="Afficher tes 15 dernières commandes du bot (éphémère)")
    async def history(interaction: discord.Interaction):
        log_command(interaction.user, "history", {}, guild=interaction.guild)
        await interaction.response.defer(thinking=True, ephemeral=True)
        gid = interaction.guild.id if interaction.guild else None
        if gid is None:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        all_items = get_recent_history(1000)
        items = [e for e in reversed(all_items) if e.get("guild_id") == gid]
        if not items:
            await interaction.followup.send("Aucune commande récente sur ce serveur.", ephemeral=True)
            return
        embed = discord.Embed(
            title="15 dernières commandes sur ce serveur",
            color=0xcccccc
        )
        for entry in items[:15]:
            t = entry["timestamp"]
            user = entry["user"]
            cmd = entry["command"]
            params = entry.get("params", {})
            ptxt = ', '.join(f"{k}={v!r}" for k, v in params.items() if v is not None)
            txt = f"`{t}` - **{user}** : /{cmd} {ptxt}"
            embed.add_field(name="\u200b", value=txt[:1000], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)