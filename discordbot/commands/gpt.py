import discord
from discord import app_commands
import tempfile
import asyncio
from gpt_util import run_gpt
from tts_util import run_tts
from audio_player import play_audio, get_voice_channel
from history import log_command

DEFAULT_GPT_PROMPT = (
    "You are a helpful assistant. Reply in the language in which the question is asked, either English or French."
)
_guild_gpt_prompt = {}
_guild_gpt_prompt_reset_task = {}

def _cancel_task(task):
    if task and not task.done():
        task.cancel()

async def _delayed_reset_gpt(gid):
    await asyncio.sleep(24 * 3600)
    _guild_gpt_prompt[gid] = DEFAULT_GPT_PROMPT
    _guild_gpt_prompt_reset_task[gid] = None

async def setup(bot):
    @bot.tree.command(
        name="gpt",
        description="Pose une question à GPT-4o puis lit la réponse"
    )
    @app_commands.describe(
        query="Question à GPT",
        lecture_vocale="Lire la réponse en vocal",
        prompt="Prompt optionnel",
        sauvegarder_prompt="Sauver ce prompt 24h"
    )
    async def gpt(
        interaction: discord.Interaction,
        query: str,
        lecture_vocale: bool = True,
        prompt: str = None,
        sauvegarder_prompt: bool = False
    ):
        log_command(
            interaction.user, "gpt",
            {
                "query": query,
                "lecture_vocale": lecture_vocale,
                "prompt": prompt,
                "sauvegarder_prompt": sauvegarder_prompt
            },
            guild=interaction.guild
        )
        gid = interaction.guild.id if interaction.guild else None
        if gid not in _guild_gpt_prompt:
            _guild_gpt_prompt[gid] = DEFAULT_GPT_PROMPT

        if prompt is not None and sauvegarder_prompt:
            _guild_gpt_prompt[gid] = prompt
            _cancel_task(_guild_gpt_prompt_reset_task.get(gid))
            _guild_gpt_prompt_reset_task[gid] = asyncio.create_task(_delayed_reset_gpt(gid))
            info = "(Prompt GPT sauvegardé 24h.)"
        else:
            info = ""
        system_prompt = prompt if prompt is not None else _guild_gpt_prompt[gid]
        await interaction.response.defer(thinking=True)
        loop = asyncio.get_running_loop()
        try:
            reply = await asyncio.wait_for(
                loop.run_in_executor(None, run_gpt, query, system_prompt),
                timeout=22
            )
        except Exception as ex:
            await interaction.followup.send(f"Erreur GPT : {ex}", ephemeral=True)
            return

        # Reply as embed
        embed = discord.Embed(title="Réponse GPT-4o",
                              color=0x00bcff,
                              description=f"**Q :** {query[:800]}")
        for idx, chunk in enumerate([reply[i:i+950] for i in range(0, len(reply), 950)][:25]):
            name = "Réponse" if idx == 0 else f"(suite {idx})"
            embed.add_field(name=name, value=chunk, inline=False)
        await interaction.followup.send(embed=embed)
        if info:
            await interaction.followup.send(info)
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
                    import os
                    os.remove(filename)
                except:
                    pass
            await interaction.followup.send("Réponse lue dans le salon vocal.")