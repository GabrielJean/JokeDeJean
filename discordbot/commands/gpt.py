import discord
from discord import app_commands
import tempfile
import asyncio
from gpt_util import run_gpt
from tts_util import run_tts
from audio_player import play_audio, get_voice_channel
from history import log_command
import os

DEFAULT_GPT_PROMPT = (
    "You are a helpful assistant. Reply in the language in which the question is asked, either English or French."
)

# -------- GPT Interactive View and Modal --------

class GPTQuestionModal(discord.ui.Modal):
    def __init__(self, parent_view, bot_name: str):
        super().__init__(title=f"Pose une question à {bot_name}")
        self.parent_view = parent_view

        self.question = discord.ui.TextInput(
            label="Question à poser",
            placeholder="Tape ta question ici",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=600,
            default=parent_view.question if parent_view.question else ""
        )
        self.prompt = discord.ui.TextInput(
            label="Prompt système (optionnel)",
            placeholder="Ex: tu es un expert en SQL...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=600,
            default=parent_view.prompt if parent_view.prompt else ""
        )
        self.add_item(self.question)
        self.add_item(self.prompt)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.question = self.question.value.strip()
        self.parent_view.prompt = self.prompt.value.strip() if self.prompt.value else None
        self.parent_view.rebuild_items()
        await interaction.response.edit_message(
            content=self.parent_view.build_content(),
            view=self.parent_view
        )

class GPTEditButton(discord.ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="📝 Modifier Question \u0026 Prompt", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GPTQuestionModal(self.parent_view, self.parent_view.bot_display_name))

class LectureVocaleSelect(discord.ui.Select):
    def __init__(self, parent_view):
        super().__init__(
            placeholder="Lecture vocale ?",
            options=[
                discord.SelectOption(label="🔊 Lire dans le vocal", value="yes", default=parent_view.lecture_vocale),
                discord.SelectOption(label="🔇 Pas de vocal", value="no", default=not parent_view.lecture_vocale)
            ],
            min_values=1, max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.lecture_vocale = self.values[0] == "yes"
        self.parent_view.rebuild_items()
        await interaction.response.edit_message(
            view=self.parent_view,
            content=self.parent_view.build_content()
        )

class GPTSubmitButton(discord.ui.Button):
    def __init__(self, parent_view):
        label = f"💡 Envoyer à {parent_view.bot_display_name} !"
        super().__init__(label=label, style=discord.ButtonStyle.success, disabled=True)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        self.parent_view.update_submit_state()
        await interaction.response.edit_message(
            view=self.parent_view,
            content=self.parent_view.build_content()
        )

        await do_gpt(
            interaction,
            question=self.parent_view.question,
            prompt=self.parent_view.prompt,
            lecture_vocale=self.parent_view.lecture_vocale
        )
        self.parent_view.stop()

class GPTView(discord.ui.View):
    def __init__(self, bot, interaction: discord.Interaction, *, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.interaction = interaction
        # Resolve bot display name for this context
        if interaction.guild:
            me = interaction.guild.get_member(bot.user.id)
            self.bot_display_name = me.display_name if me else bot.user.display_name
        else:
            self.bot_display_name = bot.user.display_name

        # Data
        self.question = ""
        self.prompt = None
        self.lecture_vocale = True

        self.rebuild_items()

    def rebuild_items(self):
        # Remove all old children
        for item in list(self.children):
            self.remove_item(item)

        self.edit_button = GPTEditButton(self)
        self.add_item(self.edit_button)
        self.add_item(LectureVocaleSelect(self))
        self.valide_button = GPTSubmitButton(self)
        self.update_submit_state()
        self.add_item(self.valide_button)

    def build_content(self):
        res = [f"**Pose une question à {self.bot_display_name} !**"]
        res.append(f"**Question:** {self.question or '_Aucune question renseignée._'}")
        if self.prompt:
            res.append(f"**Prompt système personnalisé :**\n> _{self.prompt}_")
        res.append(f"**Lire la réponse en vocal** : {'🔊 Oui' if self.lecture_vocale else '🔇 Non'}")
        return "\n".join(res)

    def update_submit_state(self):
        # Always update the submit button's state
        if hasattr(self, 'valide_button'):
            self.valide_button.disabled = not (self.question and len(self.question.strip()) > 1)

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

# ------- Main GPT Logic ------

async def do_gpt(interaction, question, prompt, lecture_vocale):
    log_command(
        interaction.user, "gpt",
        {
            "query": question,
            "prompt": prompt,
            "lecture_vocale": lecture_vocale
        },
        guild=interaction.guild
    )
    # Determine bot display name for messages
    if interaction.guild:
        me = interaction.guild.get_member(interaction.client.user.id)
        bot_display_name = me.display_name if me else interaction.client.user.display_name
    else:
        bot_display_name = interaction.client.user.display_name
    await interaction.followup.send(f"Envoi à {bot_display_name}...", ephemeral=True)
    # use default prompt unless user customizes
    # Add concise output hint to reduce empty content on small models
    base_system = prompt if prompt else DEFAULT_GPT_PROMPT
    system_prompt = base_system + " Reply in 1–2 short sentences."
    loop = asyncio.get_running_loop()
    try:
        # Allow longer answers in /gpt: ~600 completion tokens
        reply = await asyncio.wait_for(
            loop.run_in_executor(None, run_gpt, question, system_prompt, 600),
            timeout=22
        )
    except Exception as ex:
        await interaction.followup.send(f"Erreur GPT : {ex}", ephemeral=True)
        return

    # Reply as embed
    embed = discord.Embed(title=f"Réponse {bot_display_name}",
                          color=0x00bcff,
                          description=f"**Q :** {question[:800]}")
    for idx, chunk in enumerate([reply[i:i+950] for i in range(0, len(reply), 950)][:25]):
        name = "Réponse" if idx == 0 else f"(suite {idx})"
        embed.add_field(name=name, value=chunk, inline=False)
    await interaction.followup.send(embed=embed)
    vc_channel = None
    if lecture_vocale and (interaction.user.voice and interaction.user.voice.channel):
        vc_channel = interaction.user.voice.channel
    if lecture_vocale and vc_channel and reply:
        short_reply = reply[:500]
        instructions = "Lis la réponse d'une voix naturelle avec un ton informatif."
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            filename = tmp.name
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, short_reply, filename, "ash", instructions),
                timeout=20
            )
            if success:
                await asyncio.wait_for(play_audio(interaction, filename, vc_channel), timeout=30)
        except Exception:
            pass
        finally:
            try:
                os.remove(filename)
            except Exception:
                pass
        await interaction.followup.send("Réponse lue dans le salon vocal.")

# --------- Command Setup --------

async def setup(bot):
    @bot.tree.command(
        name="gpt",
        description="Pose une question au bot en mode interactif"
    )
    async def gpt(interaction: discord.Interaction):
        view = GPTView(bot, interaction)
        await interaction.response.send_message(
            content=view.build_content(),
            view=view,
            ephemeral=True
        )