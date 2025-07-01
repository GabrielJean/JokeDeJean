import discord
from discord import app_commands
import tempfile
import asyncio

from tts_util import run_tts
from audio_player import play_audio, get_voice_channel, skip_audio
from history import log_command

# Robust embed builder with Discord field/size limits
def build_safe_tts_embed(message: str, instructions: str, display_name: str):
    max_overall = 6000
    max_title = 256
    max_footer = 2048
    max_field = 1024
    max_fields = 25
    max_chunk = 950
    parts = []
    rest = message or ""
    while rest:
        parts.append(rest[:max_chunk])
        rest = rest[max_chunk:]
    embed = discord.Embed(
        title="💬 Texte prononcé en vocal"[:max_title],
        color=0x00bcff,
    )
    # If small, put in description
    if len(message) <= max_chunk and len(message) + len(embed.title) < (max_overall - 128):
        embed.description = message
    total_chars = len(embed.title or "") + len(embed.description or "")
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

async def setup(bot):
    @bot.tree.command(
        name="say-vc",
        description="Lecture TTS en vocal"
    )
    @app_commands.describe(
        message="Texte à lire",
        instructions="Style de la voix (optionnel)",
        sauvegarder_instructions="Réutiliser le style 24h",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def say_vc(
        interaction: discord.Interaction,
        message: str,
        instructions: str = None,
        sauvegarder_instructions: bool = False,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "say_vc",
            {
                "message": message,
                "instructions": instructions,
                "sauvegarder_instructions": sauvegarder_instructions,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        loop = asyncio.get_running_loop()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            filename = tmp.name
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_tts, message, filename, "ash", instructions or "Parle avec un accent québécois stéréotypé."),
                timeout=20
            )
            if not success:
                await interaction.followup.send("Erreur lors de la génération de la synthèse vocale.", ephemeral=True)
                return
            # queue play, but DO NOT await
            asyncio.create_task(play_audio(interaction, filename, vc_channel))
            # Send an embed with safe splitting
            embed = build_safe_tts_embed(message, instructions, interaction.user.display_name)
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as exc:
            await interaction.followup.send(f"Erreur : {exc}", ephemeral=True)

    @bot.tree.command(
        name="next",
        description="Passe au prochain message TTS en vocal (skip la lecture actuelle)"
    )
    @app_commands.describe(
        voice_channel="Salon vocal cible (optionnel, sinon celui où vous êtes actuellement)"
    )
    async def next_tts(
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "next",
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