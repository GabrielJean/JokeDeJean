import discord
from discord import app_commands
import tempfile
import asyncio
from gpt_util import run_gpt
from tts_util import run_tts
from audio_player import play_audio, get_voice_channel, skip_audio_by_guild  # Add skip_audio_by_guild import
from history import log_command
from guild_settings import get_tts_instructions_for
import os

# --- UI Components (adapted from roast.py) ---

class MemberSelect(discord.ui.Select):
    def __init__(self, members, parent_view, current_id=None):
        options = [
            discord.SelectOption(
                label=m.display_name,
                value=str(m.id),
                default=(str(m.id) == str(current_id))
            )
            for m in members
        ]
        if not options:
            options = [discord.SelectOption(label="Aucun membre", value="none", default=True)]
            disabled = True
        else:
            disabled = False
        super().__init__(
            placeholder="Choisir la cible du compliment...",
            options=options,
            min_values=1,
            max_values=1,
            disabled=disabled
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if self.values and self.values[0] != "none":
            self.parent_view.chosen_target_id = int(self.values[0])
        else:
            self.parent_view.chosen_target_id = None
        self.parent_view.build_selects()
        self.parent_view.update_start_button()
        await interaction.response.edit_message(
            view=self.parent_view,
            content=self.parent_view.build_content()
        )

class IntensitySelect(discord.ui.Select):
    def __init__(self, parent_view, default=2):
        options = [
            discord.SelectOption(label="Gentil (1)", value="1", default=(default == 1)),
            discord.SelectOption(label="Chaleureux (2)", value="2", default=(default == 2)),
            discord.SelectOption(label="Élogieux (3)", value="3", default=(default == 3)),
            discord.SelectOption(label="Flatteur (4)", value="4", default=(default == 4)),
            discord.SelectOption(label="Épique (5)", value="5", default=(default == 5)),
        ]
        super().__init__(
            placeholder="Niveau d'intensité",
            options=options,
            min_values=1, max_values=1,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.chosen_intensite = int(self.values[0])
        self.parent_view.build_selects()
        await interaction.response.edit_message(
            view=self.parent_view,
            content=self.parent_view.build_content()
        )

class ComplimentDetailsButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="Ajouter un détail", style=discord.ButtonStyle.secondary)
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        parent_view = self.parent_view

        class DetailModal(discord.ui.Modal, title="Ajouter un détail pour le compliment"):
            details = discord.ui.TextInput(
                label="Détail ou qualité à flatter",
                style=discord.TextStyle.paragraph,
                default=parent_view.details
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                if self.details.value.strip():
                    parent_view.details = self.details.value.strip()
                else:
                    parent_view.details = ""
                await modal_interaction.response.edit_message(
                    view=parent_view,
                    content=parent_view.build_content()
                )

        await interaction.response.send_modal(DetailModal())

class ComplimentStartButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="Démarrer le Compliment !", style=discord.ButtonStyle.success, disabled=True)
        self.parent_view = view
    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        await interaction.response.edit_message(
            view=self.parent_view,
            content=self.parent_view.build_content()
        )
        await do_compliment(
            interaction,
            cible_id=self.parent_view.chosen_target_id,
            intensite=self.parent_view.chosen_intensite,
            details=self.parent_view.details
        )
        self.view.stop()

class ComplimentSetupView(discord.ui.View):
    def __init__(self, bot, interaction: discord.Interaction, voice_members, *, timeout=120):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.interaction = interaction
        self.members = voice_members
        self.chosen_target_id = None
        self.chosen_intensite = 2
        self.details = ""
        self.demarrer_button = ComplimentStartButton(self)
        self.build_selects()
        self.add_item(ComplimentDetailsButton(self))
        self.add_item(self.demarrer_button)
    def build_selects(self):
        for item in list(self.children):
            if isinstance(item, (MemberSelect, IntensitySelect)):
                self.remove_item(item)
        self.add_item(MemberSelect(self.members, self, self.chosen_target_id))
        self.intensite_select = IntensitySelect(self, default=self.chosen_intensite)
        self.add_item(self.intensite_select)
    def update_start_button(self):
        self.demarrer_button.disabled = self.chosen_target_id is None or not self.members
    def details_line(self):
        return f"**Détail actuellement ajouté :**\n> _{self.details}_" if self.details else "Aucun détail ajouté pour l'instant."
    def build_content(self):
        return (
            "Sélectionne la cible, l'intensité, et lance ton compliment :\n"
            f"{self.details_line()}"
        )
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.interaction.edit_original_response(
                content=self.build_content(),
                view=self
            )
        except Exception:
            pass

# --- Stop Playback View (copied from roast.py) ---

class StopPlaybackView(discord.ui.View):
    def __init__(self, guild_id: int, initiator_id: int, *, timeout=120):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.initiator_id = initiator_id

    @discord.ui.button(label="⏹️ Arrêter la lecture", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.initiator_id:
            await interaction.response.send_message(
                "Seul celui qui a lancé la lecture peut l'arrêter.",
                ephemeral=True
            )
            return
        success = skip_audio_by_guild(self.guild_id)
        if success:
            await interaction.response.send_message(
                "Lecture stoppée et bot déconnecté du vocal.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Pas de lecture en cours.",
                ephemeral=True
            )
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.NotFound:
            pass
        except Exception:
            pass
        self.stop()

# --- Play audio and cleanup after playback (copied from roast.py) ---

async def play_audio_and_cleanup(interaction, filename, vc_channel):
    try:
        await play_audio(interaction, filename, vc_channel)
    finally:
        try:
            os.remove(filename)
        except Exception:
            pass

# --- Main compliment logic ---
async def do_compliment(interaction, cible_id, intensite, details, voice_channel: discord.VoiceChannel = None):
    guild = interaction.guild
    cible = guild.get_member(int(cible_id)) if cible_id and cible_id != "none" else None
    if cible is None:
        await interaction.followup.send("Impossible de trouver la cible dans ce serveur.", ephemeral=True)
        return
    intensite = max(1, min(5, int(intensite)))
    noms_intensite = {
        1: "gentil",
        2: "chaleureux",
        3: "élogieux",
        4: "flatteur",
        5: "épique"
    }
    username = cible.display_name
    ajout_details = f" Met en valeur : {details}" if details else ""
    prompt_gpt = (
        f"Fais un compliment fun à '{username}'. "
        f"Niveau {intensite}/5 : {noms_intensite[intensite]}. "
        f"{ajout_details} "
        "Accent humoriste québécois, max 4 phrases."
    )
    titre = f"Compliment pour {username} (niv. {intensite})"
    loop = asyncio.get_running_loop()
    try:
        texte = await asyncio.wait_for(
            loop.run_in_executor(
                None, run_gpt, prompt_gpt, "Compliments québécois.", 250
            ),
            timeout=18
        )
    except Exception as ex:
        await interaction.followup.send(
            f"Erreur génération compliment: {ex}", ephemeral=True
        )
        return
    embed = discord.Embed(title=titre, description=texte[:1024], color=0x41d98e)
    await interaction.followup.send(embed=embed)
    log_command(
        interaction.user, "compliment",
        {
            "cible": username,
            "intensite": intensite,
            "details": details,
            "voice_channel": str(voice_channel) if voice_channel else None
        },
        guild=interaction.guild
    )
    # Vocal
    vc_channel = get_voice_channel(interaction, voice_channel)
    if vc_channel:
        instructions = get_tts_instructions_for(interaction.guild, "compliment", "Parle avec un accent québécois stéréotypé.")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            filename = tmp.name
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, texte, filename, "ash", instructions),
                timeout=20
            )
            if success:
                asyncio.create_task(play_audio_and_cleanup(interaction, filename, vc_channel))
                view = StopPlaybackView(interaction.guild.id, interaction.user.id)
                await interaction.followup.send(
                    "Compliment lancé au vocal!", ephemeral=True, view=view
                )
            else:
                await interaction.followup.send("Erreur lors de la génération audio TTS.", ephemeral=True)
        except Exception:
            await interaction.followup.send("Erreur lors de la génération ou la lecture audio.", ephemeral=True)
    else:
        await interaction.followup.send("(Rejoins ou précise un salon vocal !)", ephemeral=True)

# --- Command registration ---

async def setup(bot):
    @bot.tree.command(
        name="compliment",
        description="Compose un compliment (UI si aucun paramètre)"
    )
    @app_commands.describe(
        cible="Membre à complimenter (si vide, ouvre l'UI)",
        intensite="Intensité de 1 à 5 (par défaut 2)",
        details="Détails à mettre en valeur (optionnel)",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def compliment(
        interaction: discord.Interaction,
        cible: discord.Member = None,
        intensite: int = None,
        details: str = None,
        voice_channel: discord.VoiceChannel = None
    ):
        # Route UI si aucun paramètre fourni
        if cible is None and intensite is None and (details is None or details.strip() == ""):
            user = interaction.user
            if not user.voice or not user.voice.channel:
                await interaction.response.send_message(
                    "Tu dois être dans un salon vocal pour lancer cette commande.", ephemeral=True
                )
                return
            voice_channel_cur = user.voice.channel
            voice_members = [m for m in voice_channel_cur.members if not m.bot]
            if not voice_members:
                await interaction.response.send_message(
                    "Aucun membre humain trouvé dans ton salon vocal.", ephemeral=True
                )
                return
            view = ComplimentSetupView(bot, interaction, voice_members)
            await interaction.response.send_message(
                view=view,
                ephemeral=True,
                content=view.build_content()
            )
            return

        # Exécution directe avec paramètres
        if not cible:
            await interaction.response.send_message(
                "Spécifie la cible (cible=@membre) ou utilise la version UI sans paramètres.",
                ephemeral=True
            )
            return
        level = 2 if intensite is None else max(1, min(5, int(intensite)))
        det = details.strip() if details else ""
        await interaction.response.defer(thinking=True, ephemeral=True)
        await do_compliment(
            interaction,
            cible_id=cible.id,
            intensite=level,
            details=det,
            voice_channel=voice_channel
        )
