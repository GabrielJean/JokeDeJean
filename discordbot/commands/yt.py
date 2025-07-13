import discord
from discord import app_commands
import asyncio
import yt_dlp
from audio_player import play_audio, play_ytdlp_stream, get_voice_channel, skip_audio_by_guild
from history import log_command
from concurrent.futures import ProcessPoolExecutor

YTDLP_EXECUTOR = ProcessPoolExecutor(max_workers=6)

def ytdlp_get_info(url):
    with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, "format": "bestaudio"}) as ydl:
        return ydl.extract_info(url, download=False)

def ytdlp_search(query):
    with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, "format": "bestaudio"}) as ydl:
        return ydl.extract_info(f"ytsearch3:{query}", download=False)['entries']

class StopPlaybackView(discord.ui.View):
    def __init__(self, guild_id: int, initiator_id: int, *, timeout=900):
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

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True

async def setup(bot):
    @bot.tree.command(
        name="yt",
        description="Joue l'audio d'une vidéo YouTube dans le vocal"
    )
    @app_commands.describe(
        url="Lien YouTube",
        voice_channel="Salon vocal cible (optionnel)",
        loop="Lire en boucle (redémarrer quand fini)"
    )
    async def yt(
        interaction: discord.Interaction,
        url: str,
        voice_channel: discord.VoiceChannel = None,
        loop: bool = False
    ):
        log_command(
            interaction.user, "yt",
            {
                "url": url,
                "voice_channel": str(voice_channel) if voice_channel else None,
                "loop": loop,
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True, ephemeral=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        loop_async = asyncio.get_running_loop()
        try:
            info = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, url)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors de la récupération d'info : {exc}", ephemeral=True)
            return
        duration = info.get("duration")
        video_title = info.get("title", "Vidéo YouTube")
        video_url = info.get("webpage_url", url)
        view = StopPlaybackView(interaction.guild.id, interaction.user.id, timeout=900)
        loop_msg = " (en boucle)" if loop else ""
        await interaction.followup.send(
            f"Lecture audio YouTube{loop_msg} lancée dans le salon vocal.\n"
            "Regardez ce salon pour la barre de progression !",
            ephemeral=True,
            view=view
        )
        asyncio.create_task(
            play_ytdlp_stream(
                interaction,
                info,
                vc_channel,
                duration=duration,
                title=video_title,
                video_url=video_url,
                announce_message=True,
                loop=loop,
            )
        )

    @bot.tree.command(
        name="ytsearch",
        description="Recherche une vidéo YouTube et joue l'audio dans le vocal"
    )
    @app_commands.describe(
        query="Recherche YouTube",
        voice_channel="Salon vocal cible (optionnel)",
        loop="Lire en boucle (redémarrer quand fini)"
    )
    async def ytsearch(
        interaction: discord.Interaction,
        query: str,
        voice_channel: discord.VoiceChannel = None,
        loop: bool = False
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop_async = asyncio.get_running_loop()
        try:
            results = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_search, query)
            filtered_results = [
                entry for entry in results
                if entry.get('duration') is not None
            ]
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors de la recherche : {exc}", ephemeral=True)
            return
        if not filtered_results:
            await interaction.followup.send("Aucun résultat trouvé.", ephemeral=True)
            return
        display_n = min(3, len(filtered_results))  # Show only top 3 videos
        results = filtered_results[:display_n]
        out_lines = []
        for idx, entry in enumerate(results, 1):
            duration = entry.get('duration')
            duration_str = f"{duration//60}:{duration%60:02d}" if duration else "??:??"
            title = entry['title']
            url = entry['webpage_url']
            uploader = entry.get('uploader', '')
            out_lines.append(f"**{idx}.** [{title[:80]}]({url}) (`{duration_str}`) — *{uploader[:32]}*")
        out_text = "**Voici les résultats de la recherche :**\n\n" + "\n".join(out_lines)
        out_text += "\n\n**Sélectionnez la vidéo à jouer ci-dessous :**"

        class YTSelectView(discord.ui.View):
            def __init__(self, results):
                super().__init__(timeout=60)
                options = [
                    discord.SelectOption(
                        label=f"{entry['title'][:80]}",
                        description=f"{entry.get('uploader', '')[:50]} | {entry.get('duration', 0)//60}:{entry.get('duration', 0)%60:02d}",
                        value=str(idx)
                    ) for idx, entry in enumerate(results)
                ]
                self.select = discord.ui.Select(
                    placeholder="Cliquez pour choisir une vidéo à jouer...",
                    min_values=1,
                    max_values=1,
                    options=options
                )
                self.select.callback = self.select_callback
                self.add_item(self.select)
                self.results = results

            async def select_callback(self, select_interaction: discord.Interaction):
                if select_interaction.user.id != interaction.user.id:
                    await select_interaction.response.send_message(
                        "Seul l'utilisateur ayant fait la commande peut sélectionner.",
                        ephemeral=True
                    )
                    return
                choice = int(self.select.values[0])
                entry = self.results[choice]
                url = entry['webpage_url']
                title = entry['title']
                duration = entry.get("duration")
                vc_channel = get_voice_channel(select_interaction, voice_channel)
                if not vc_channel:
                    await select_interaction.response.send_message(
                        "Vous devez être dans un salon vocal ou en préciser un.",
                        ephemeral=True
                    )
                    return
                await select_interaction.response.defer(ephemeral=True)
                try:
                    info = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, url)
                except Exception as exc:
                    await select_inter_interaction.followup.send(
                        f"Erreur lors de la récupération d'info : {exc}", ephemeral=True
                    )
                    return
                view = StopPlaybackView(select_interaction.guild.id, select_interaction.user.id, timeout=900)
                loop_msg = " (en boucle)" if loop else ""
                await select_interaction.followup.send(
                    f"Lecture de {title} - {url}{loop_msg} lancée dans le salon vocal.\n"
                    "Regardez ce salon pour la barre de progression !",
                    ephemeral=True,
                    view=view
                )
                asyncio.create_task(
                    play_ytdlp_stream(
                        select_interaction,
                        info,
                        vc_channel,
                        duration=duration,
                        title=title,
                        video_url=url,
                        announce_message=True,
                        loop=loop,
                    )
                )
                self.stop()

        view = YTSelectView(results)
        await interaction.followup.send(content=out_text, view=view, ephemeral=True)
