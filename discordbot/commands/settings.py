import discord
from discord import app_commands
from history import log_command
from guild_settings import get_guild_settings, set_guild_setting, reset_guild_settings, clear_guild_setting, get_tts_instructions_for

async def setup(bot):
    # ----- UI Components -----
    class TargetSelect(discord.ui.Select):
        def __init__(self, parent_view, default_value: str = "global"):
            options = [
                discord.SelectOption(label="Global (défaut)", value="global", default=(default_value=="global")),
                discord.SelectOption(label="say-vc", value="say-vc", default=(default_value=="say-vc")),
                discord.SelectOption(label="roast", value="roast", default=(default_value=="roast")),
                discord.SelectOption(label="compliment", value="compliment", default=(default_value=="compliment")),
            ]
            super().__init__(placeholder="Cible à modifier", options=options, min_values=1, max_values=1)
            self.parent_view = parent_view
        async def callback(self, interaction: discord.Interaction):
            self.parent_view.target = self.values[0]
            self.parent_view.rebuild_items()
            await interaction.response.edit_message(content=self.parent_view.build_content(), view=self.parent_view)

    class EditModal(discord.ui.Modal):
        def __init__(self, parent_view, current_text: str):
            super().__init__(title="Modifier les instructions TTS")
            self.parent_view = parent_view
            self.instructions = discord.ui.TextInput(
                label="Instructions TTS",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=400,
                default=current_text or ""
            )
            self.add_item(self.instructions)
        async def on_submit(self, interaction: discord.Interaction):
            gid = interaction.guild.id
            key = self.parent_view.target_key()
            new_val = self.instructions.value.strip()
            set_guild_setting(gid, key, new_val)
            log_command(interaction.user, "settings", {key: new_val}, guild=interaction.guild)
            self.parent_view.last_message = "✅ Instructions mises à jour."
            self.parent_view.rebuild_items()
            await interaction.response.edit_message(content=self.parent_view.build_content(), view=self.parent_view)

    class EditButton(discord.ui.Button):
        def __init__(self, view):
            super().__init__(label="📝 Modifier", style=discord.ButtonStyle.primary)
            self.parent_view = view
        async def callback(self, interaction: discord.Interaction):
            gid = interaction.guild.id
            current = self.parent_view.current_value(gid)
            await interaction.response.send_modal(EditModal(self.parent_view, current))

    class ResetSelectedButton(discord.ui.Button):
        def __init__(self, view):
            super().__init__(label="↩️ Reset (cible)", style=discord.ButtonStyle.secondary)
            self.parent_view = view
        async def callback(self, interaction: discord.Interaction):
            gid = interaction.guild.id
            key = self.parent_view.target_key()
            clear_guild_setting(gid, key)
            log_command(interaction.user, "settings", {"reset_field": key}, guild=interaction.guild)
            self.parent_view.last_message = f"✅ Champ {key} réinitialisé."
            self.parent_view.rebuild_items()
            await interaction.response.edit_message(content=self.parent_view.build_content(), view=self.parent_view)

    class ResetAllButton(discord.ui.Button):
        def __init__(self, view):
            super().__init__(label="🧹 Reset (tout)", style=discord.ButtonStyle.danger)
            self.parent_view = view
        async def callback(self, interaction: discord.Interaction):
            gid = interaction.guild.id
            reset_guild_settings(gid)
            log_command(interaction.user, "settings", {"reset": True}, guild=interaction.guild)
            self.parent_view.last_message = "✅ Tous les réglages ont été réinitialisés."
            self.parent_view.rebuild_items()
            await interaction.response.edit_message(content=self.parent_view.build_content(), view=self.parent_view)

    class SettingsView(discord.ui.View):
        def __init__(self, interaction: discord.Interaction, *, timeout=180):
            super().__init__(timeout=timeout)
            self.interaction = interaction
            self.target = "global"
            self.last_message = None
            self.rebuild_items()
        def target_key(self) -> str:
            return {
                "global": "tts_instructions",
                "say-vc": "tts_say_vc",
                "roast": "tts_roast",
                "compliment": "tts_compliment",
            }[self.target]
        def current_value(self, gid: int) -> str:
            s = get_guild_settings(gid)
            key = self.target_key()
            if key in s and s[key]:
                return s[key]
            # fallback preview
            if self.target != "global":
                # show effective value
                feature = "say_vc" if self.target == "say-vc" else self.target
                return get_tts_instructions_for(self.interaction.guild, feature, s.get("tts_instructions"))
            return s.get("tts_instructions")
        def rebuild_items(self):
            for item in list(self.children):
                self.remove_item(item)
            self.add_item(TargetSelect(self, self.target))
            self.add_item(EditButton(self))
            self.add_item(ResetSelectedButton(self))
            self.add_item(ResetAllButton(self))
        def build_content(self) -> str:
            gid = self.interaction.guild.id
            s = get_guild_settings(gid)
            lines = ["**Réglages TTS du serveur**"]
            lines.append(f"- Global: {s.get('tts_instructions')}")
            lines.append(f"- say-vc: {s.get('tts_say_vc', '(hérite du global)')}")
            lines.append(f"- roast: {s.get('tts_roast', '(hérite du global)')}")
            lines.append(f"- compliment: {s.get('tts_compliment', '(hérite du global)')}")
            lines.append("")
            lines.append(f"Cible actuelle: `{self.target}`")
            current_text = self.current_value(gid) or ""
            lines.append(f"Valeur effective: {current_text}")
            if self.last_message:
                lines.append("")
                lines.append(self.last_message)
            return "\n".join(lines)
        async def on_timeout(self):
            for child in self.children:
                if hasattr(child, 'disabled'):
                    child.disabled = True
            try:
                await self.interaction.edit_original_response(content=self.build_content(), view=self)
            except Exception:
                pass

    @bot.tree.command(
        name="settings",
        description="Voir ou modifier les réglages du serveur (UI si aucun paramètre)"
    )
    @app_commands.describe(
        target="Cible: global | say-vc | roast | compliment",
        tts_instructions="Texte d'instructions par défaut pour la voix TTS (optionnel)",
        reset="Réinitialiser tous les réglages pour ce serveur"
    )
    async def settings(
        interaction: discord.Interaction,
        target: str = None,
        tts_instructions: str = None,
        reset: bool = False
    ):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        gid = interaction.guild.id
        # If no params => open UI
        if target is None and tts_instructions is None and not reset:
            view = SettingsView(interaction)
            await interaction.response.send_message(content=view.build_content(), view=view, ephemeral=True)
            return
        # Handle parameter path
        if reset:
            reset_guild_settings(gid)
            log_command(interaction.user, "settings", {"reset": True}, guild=interaction.guild)
            await interaction.response.send_message("✅ Réglages réinitialisés pour ce serveur.", ephemeral=True)
            return
        tgt = (target or "global").lower()
        key_map = {
            "global": "tts_instructions",
            "say-vc": "tts_say_vc",
            "roast": "tts_roast",
            "compliment": "tts_compliment",
        }
        if tgt not in key_map:
            await interaction.response.send_message("Cible invalide. Utilisez: global | say-vc | roast | compliment", ephemeral=True)
            return
        if tts_instructions is not None:
            key = key_map[tgt]
            new_settings = set_guild_setting(gid, key, tts_instructions.strip())
            log_command(interaction.user, "settings", {key: tts_instructions}, guild=interaction.guild)
            await interaction.response.send_message(f"✅ `{tgt}` mis à jour.", ephemeral=True)
            return
        # No tts_instructions given: just show current
        s = get_guild_settings(gid)
        embed = discord.Embed(title="Réglages du serveur", color=0x00bcff)
        embed.add_field(name="Global", value=f"{s.get('tts_instructions')}", inline=False)
        embed.add_field(name="say-vc", value=f"{s.get('tts_say_vc', '(hérite du global)')}", inline=False)
        embed.add_field(name="roast", value=f"{s.get('tts_roast', '(hérite du global)')}", inline=False)
        embed.add_field(name="compliment", value=f"{s.get('tts_compliment', '(hérite du global)')}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

