import discord
from discord import app_commands
import tempfile
import asyncio
from gpt_util import run_gpt
from tts_util import run_tts
from audio_player import play_audio, get_voice_channel
from history import log_command

async def setup(bot):
    @bot.tree.command(
        name="compliment",
        description="Compliment personnalisé (fun)"
    )
    @app_commands.describe(
        cible="Ciblé du compliment",
        details="Infos à flatter",
        voice_channel="Salon vocal cible"
    )
    async def compliment(
        interaction: discord.Interaction,
        cible: discord.Member,
        details: str = None,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "compliment",
            {
                "cible": cible.display_name if hasattr(cible, "display_name") else str(cible),
                "details": details,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        username = cible.display_name if hasattr(cible, "display_name") else str(cible)
        ajout_details = f" Met en valeur : {details}" if details else ""
        prompt_gpt = (
            f"Fais un compliment fun à '{username}'."
            f"{ajout_details} "
            "Accentu humoriste québécois, max 4 phrases."
        )
        titre = f"Compliment pour {username}"
        await interaction.response.defer(thinking=True)
        loop = asyncio.get_running_loop()
        try:
            texte = await asyncio.wait_for(
                loop.run_in_executor(None, run_gpt, prompt_gpt, "Compliments québécois."), timeout=18)
        except Exception as ex:
            await interaction.followup.send(
                f"Erreur génération compliment: {ex}", ephemeral=True
            )
            return
        embed = discord.Embed(title=titre, description=texte[:1024], color=0x41d98e)
        await interaction.followup.send(embed=embed)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if vc_channel:
            instructions = "Parle avec un accent québécois stéréotypé."
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                filename = tmp.name
            try:
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, run_tts, texte, filename, "ash", instructions), timeout=20
                )
                if success:
                    await asyncio.wait_for(play_audio(interaction, filename, vc_channel), timeout=30)
            except Exception:
                pass
            finally:
                try: import os; os.remove(filename)
                except: pass
            await interaction.followup.send("Compliment lancé au vocal!", ephemeral=True)
        else:
            await interaction.followup.send("(Rejoins ou précise un salon vocal !)", ephemeral=True)