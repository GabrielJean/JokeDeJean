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
        name="roast",
        description="Roast drôle et custom (1 à 5)"
    )
    @app_commands.describe(
        cible="Cible du roast",
        intensite="Niveau (1: soft, 5: salé)",
        details="Infos ou mèmes à exploiter",
        voice_channel="Salon vocal cible"
    )
    async def roast(
        interaction: discord.Interaction,
        cible: discord.Member,
        intensite: int = 2,
        details: str = None,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "roast",
            {
                "cible": cible.display_name if hasattr(cible, "display_name") else str(cible),
                "intensite": intensite,
                "details": details,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        intensite = max(1, min(5, intensite))
        noms_intensite = {
            1: "très doux (taquin)",
            2: "moqueur",
            3: "grinçant",
            4: "salé",
            5: "franc-parler punchy"
        }
        username = cible.display_name if hasattr(cible, "display_name") else str(cible)
        ajout_details = ""
        if details:
            ajout_details = f" Utilise : {details}"
        prompt_gpt = (
            f"Fais un roast québécois sur '{username}'. "
            f"Niveau {intensite}/5 : {noms_intensite[intensite]}. "
            f"{ajout_details} "
            "Humour direct, accent québécois, max 4 phrases, pas d'intro."
        )
        titre = f"Roast de {username} (niv. {intensite})"
        await interaction.response.defer(thinking=True)
        loop = asyncio.get_running_loop()
        try:
            texte = await asyncio.wait_for(
                loop.run_in_executor(
                    None, run_gpt, prompt_gpt,
                    "Parle avec un accent québécois stéréotypé."
                ),
                timeout=18
            )
        except Exception as ex:
            await interaction.followup.send(
                f"Erreur génération roast: {ex}", ephemeral=True
            )
            return
        embed = discord.Embed(title=titre, description=texte[:1024], color=0xff8800 if intensite < 4 else 0xff0000)
        await interaction.followup.send(embed=embed)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if vc_channel:
            instructions = "Parle avec un accent québécois stéréotypé."
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                filename = tmp.name
            try:
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, run_tts, texte, filename, "ash", instructions),
                    timeout=20
                )
                if success:
                    await asyncio.wait_for(play_audio(interaction, filename, vc_channel), timeout=30)
            except Exception:
                pass
            finally:
                try: import os; os.remove(filename)
                except: pass
            await interaction.followup.send("Roast balancé au vocal!", ephemeral=True)
        else:
            await interaction.followup.send("(Rejoins ou précise un salon vocal !)", ephemeral=True)