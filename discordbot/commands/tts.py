import discord
from discord import app_commands
import tempfile
import asyncio
import json
import os
try:
    from ..tts_util import run_tts
    from ..audio_player import play_audio, get_voice_channel, skip_audio
    from ..history import log_command
    from ..guild_settings import get_tts_instructions_for
except ImportError:  # script fallback
    from tts_util import run_tts  # type: ignore
    from audio_player import play_audio, get_voice_channel, skip_audio  # type: ignore
    from history import log_command  # type: ignore
    from guild_settings import get_tts_instructions_for  # type: ignore

# Load config for TTS instructions
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.json'))
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

say_vc_tts_fallback = config["tts_default_instructions"]


def build_safe_tts_embed(message: str, instructions: str, display_name: str):
    max_overall = 6000
    max_title = 256
    max_footer = 2048
    max_field = 1024
    max_fields = 25
    max_chunk = 950
    embed = discord.Embed(
        title="💬 Texte prononcé en vocal"[:max_title],
        color=0x00bcff,
    )
    if len(message) <= max_chunk and len(message) + len(embed.title) < (max_overall - 128):
        embed.description = message
    else:
        parts = []
        rest = message or ""
        while rest:
            parts.append(rest[:max_chunk])
            rest = rest[max_chunk:]
        total_chars = len(embed.title or "")
        for idx, chunk in enumerate(parts[:max_fields]):
            name = "Message" if idx == 0 else f"…suite {idx}"
            field_val = chunk if len(chunk) <= max_field else (chunk[:max_field-3] + "...")
            embed.add_field(name=name, value=field_val, inline=False)
            total_chars += len(name) + len(field_val)
            if total_chars > max_overall:
                break
        if sum(len(x) for x in parts) > max_chunk * max_fields:
            embed.add_field(name="…", value="(message coupé :trop long pour Discord embed!)", inline=False)
    if instructions:
        instr_val = (instructions if len(instructions) < max_field else instructions[:max_field-3] + "...")
        embed.add_field(name="Style", value=instr_val, inline=False)
    embed.set_footer(text=f"Demandé par {display_name}"[:max_footer])
    return embed

class SayVCModal(discord.ui.Modal, title="Lire un message dans un salon vocal"):
    message = discord.ui.TextInput(
        label="Texte à lire",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=3,
        max_length=1800,
        placeholder="Que dois-je lire dans le vocal ?"
    )
    instructions = discord.ui.TextInput(
        label="Style de voix (optionnel)",
        style=discord.TextStyle.short,
        required=False,
        max_length=250,
        placeholder="Exemple : Ton enfantin, ou accent parisien"
    )
    async def on_submit(self, interaction: discord.Interaction):
        msg = self.message.value.strip()
        instr = self.instructions.value.strip() if self.instructions.value else None
        log_command(
            interaction.user, "say_vc",
            {
                "message": msg,
                "instructions": instr,
                "voice_channel": str(interaction.user.voice.channel) if (interaction.user.voice and interaction.user.voice.channel) else None
            },
            guild=interaction.guild
        )
        vc_channel = get_voice_channel(interaction)
        if not vc_channel:
            await interaction.response.send_message(
                "Vous devez être dans un salon vocal ou en préciser un.",
                ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=False)
        loop = asyncio.get_running_loop()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            filename = tmp.name
        try:
            style = instr or get_tts_instructions_for(interaction.guild, "say_vc", say_vc_tts_fallback)
            success_tuple = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, msg, filename, style),
                timeout=20
            )
            success = success_tuple[0] if isinstance(success_tuple, tuple) else success_tuple
            if not success:
                await interaction.followup.send("Erreur lors de la génération de la synthèse vocale.", ephemeral=True)
                return
            asyncio.create_task(play_audio(interaction, filename, vc_channel))
            embed = build_safe_tts_embed(msg, instr, interaction.user.display_name)
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as exc:
            await interaction.followup.send(f"Erreur : {exc}", ephemeral=True)

async def setup(bot):
    @bot.tree.command(
        name="say-vc",
        description="Lecture TTS en vocal (UI si aucun paramètre)"
    )
    @app_commands.describe(
        message="Texte à lire (si vide, ouvre une fenêtre)",
        instructions="Style de voix (optionnel)",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def say_vc(
        interaction: discord.Interaction,
        message: str = None,
        instructions: str = None,
        voice_channel: discord.VoiceChannel = None
    ):
        from ..tts_util import run_voice_verbatim_tts
        if not message or not message.strip():
            await interaction.response.send_modal(SayVCModal())
            return

        # Exécution directe avec paramètres
        from tts_util import run_voice_verbatim_tts  # type: ignore
        instr = instructions.strip() if instructions else None
        log_command(
            interaction.user, "say_vc",
            {
                "message": msg,
                "instructions": instr,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.response.send_message(
                "Vous devez être dans un salon vocal ou en préciser un.",
                ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=False)
        loop = asyncio.get_running_loop()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            filename = tmp.name
        try:
            style = instr or get_tts_instructions_for(interaction.guild, "say_vc", say_vc_tts_fallback)
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_voice_verbatim_tts, msg, filename, style, "Leo", 16000),
                timeout=25
            )
            if not success:
                await interaction.followup.send("Erreur lors de la génération de la synthèse vocale.", ephemeral=True)
                return
            asyncio.create_task(play_audio(interaction, filename, vc_channel))
            embed = build_safe_tts_embed(msg, instr, interaction.user.display_name)
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as exc:
            await interaction.followup.send(f"Erreur : {exc}", ephemeral=True)

    @bot.tree.command(
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_voice_verbatim_tts, msg, filename, style, "Leo", 16000),
                timeout=25
    @app_commands.describe(
    )
    async def skip_tts(
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "skip",
            {
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        try:
            skipped = skip_audio(vc_channel)
            if skipped:
                await interaction.followup.send(f"⏭️ Lecture avancée au prochain message dans {vc_channel.mention}.")
            else:
                await interaction.followup.send("Aucune lecture en cours ou file d'attente vide.", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors du skip : {exc}", ephemeral=True)
