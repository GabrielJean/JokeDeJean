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

class YTSearchModal(discord.ui.Modal, title="Recherche YouTube"):
    search_query = discord.ui.TextInput(
        label="Recherche",
        placeholder="Tapez votre recherche YouTube...",
        min_length=2,
        max_length=120,
        required=True,
    )

    def __init__(self, on_complete, *a, **kw):
        super().__init__(*a, **kw)
        self.on_complete = on_complete

    async def on_submit(self, interaction: discord.Interaction):
        search_query = self.search_query.value
        await self.on_complete(interaction, search_query)

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
        is_live = bool(info.get("is_live")) or info.get("live_status") == "is_live"
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
                is_live=is_live,
            )
        )

    @bot.tree.command(
        name="ytsearch",
        description="Recherche une vidéo YouTube et joue l'audio dans le vocal (popup)"
    )
    @app_commands.describe(
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def ytsearch(
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel = None,
    ):
        async def on_complete(inter: discord.Interaction, search_query: str):
            await inter.response.defer(thinking=True, ephemeral=True)
            loop_async = asyncio.get_running_loop()
            try:
                results = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_search, search_query)
                filtered_results = [
                    entry for entry in results
                    if entry.get('duration') is not None or entry.get('is_live') or entry.get('live_status') == "is_live"
                ]
            except Exception as exc:
                await inter.followup.send(f"Erreur lors de la recherche : {exc}", ephemeral=True)
                return
            if not filtered_results:
                await inter.followup.send("Aucun résultat trouvé.", ephemeral=True)
                return

            display_n = min(3, len(filtered_results))  # Show only top 3 videos
            shown_results = filtered_results[:display_n]
            out_lines = []
            for idx, entry in enumerate(shown_results, 1):
                duration = entry.get('duration')
                is_live = bool(entry.get('is_live')) or entry.get('live_status') == "is_live"
                duration_str = "LIVE" if is_live else (f"{duration//60}:{duration%60:02d}" if duration else "??:??")
                title = entry['title']
                url = entry['webpage_url']
                uploader = entry.get('uploader', '')
                out_lines.append(f"**{idx}.** {title} {url} (`{duration_str}`) — _{uploader[:32]}_")

            out_text = "**Voici les résultats de la recherche :**\n\n" + "\n".join(out_lines)
            out_text += "\n\n**Sélectionnez la vidéo et l'option boucle ci-dessous, puis cliquez sur Confirmer :**"

            class YTSelectLoopView(discord.ui.View):
                def __init__(self, results):
                    super().__init__(timeout=120)
                    self.results = results
                    self.selected_video = None
                    self.loop_value = None
                    self.message = None  # Will be set after initial send

                    # Dropdowns (init with no default)
                    self.video_select = self.build_video_select()
                    self.loop_select = self.build_loop_select()
                    self.add_item(self.video_select)
                    self.add_item(self.loop_select)

                    # Confirm Button
                    self.confirm_button = self.ConfirmButton(self)
                    self.add_item(self.confirm_button)
                    self.update_confirm_button_state()

                def build_video_select(self):
                    options = [
                        discord.SelectOption(
                            label=f"{entry['title'][:80]}",
                            description=(f"{entry.get('uploader', '')[:50]} | "
                                         + ("LIVE" if (entry.get('is_live') or entry.get("live_status") == "is_live")
                                            else f"{entry.get('duration', 0)//60}:{entry.get('duration', 0)%60:02d}")
                                         ),
                            value=str(idx),
                            default=(self.selected_video == idx)
                        ) for idx, entry in enumerate(self.results)
                    ]
                    select = self.VideoSelect(self.results, self, options)
                    return select

                def build_loop_select(self):
                    options = [
                        discord.SelectOption(label="Lecture en boucle : Non", value="false", emoji="⏹️", default=(self.loop_value is False)),
                        discord.SelectOption(label="Lecture en boucle : Oui", value="true", emoji="🔁", default=(self.loop_value is True)),
                    ]
                    select = self.LoopSelect(self, options)
                    return select

                def update_selects(self):
                    # Remove and re-add selects to update defaults
                    self.remove_item(self.video_select)
                    self.remove_item(self.loop_select)
                    self.video_select = self.build_video_select()
                    self.loop_select = self.build_loop_select()
                    self.add_item(self.video_select)
                    self.add_item(self.loop_select)

                def update_confirm_button_state(self):
                    is_ready = self.selected_video is not None and self.loop_value is not None
                    self.confirm_button.disabled = not is_ready

                class VideoSelect(discord.ui.Select):
                    def __init__(self, results, parent_view, options):
                        super().__init__(
                            placeholder="Choisissez une vidéo à jouer...",
                            min_values=1,
                            max_values=1,
                            options=options,
                            custom_id="video_select"
                        )
                        self.parent_view = parent_view
                        self.results = results

                    async def callback(self, interaction: discord.Interaction):
                        self.parent_view.selected_video = int(self.values[0])
                        self.parent_view.update_selects()  # will rebuild selects with new default
                        self.parent_view.update_confirm_button_state()
                        if self.parent_view.message:
                            await self.parent_view.message.edit(view=self.parent_view)
                        await interaction.response.defer()

                class LoopSelect(discord.ui.Select):
                    def __init__(self, parent_view, options):
                        super().__init__(
                            placeholder="Lecture en boucle ?",  # This is always visible until selection
                            min_values=1,
                            max_values=1,
                            options=options,
                            custom_id="loop_select"
                        )
                        self.parent_view = parent_view

                    async def callback(self, interaction: discord.Interaction):
                        self.parent_view.loop_value = self.values[0] == "true"
                        self.parent_view.update_selects()  # will rebuild selects with new default
                        self.parent_view.update_confirm_button_state()
                        if self.parent_view.message:
                            await self.parent_view.message.edit(view=self.parent_view)
                        await interaction.response.defer()

                class ConfirmButton(discord.ui.Button):
                    def __init__(self, parent_view):
                        super().__init__(
                            label="Confirmer",
                            style=discord.ButtonStyle.success,
                            disabled=True
                        )
                        self.parent_view = parent_view

                    async def callback(self, interaction: discord.Interaction):
                        view = self.parent_view
                        idx = view.selected_video
                        loop = view.loop_value
                        entry = view.results[idx]
                        url = entry['webpage_url']
                        title = entry['title']
                        duration = entry.get("duration")
                        is_live = bool(entry.get("is_live")) or entry.get("live_status") == "is_live"
                        vc_channel = get_voice_channel(interaction, voice_channel)
                        if not vc_channel:
                            await interaction.response.send_message(
                                "Vous devez être dans un salon vocal ou en préciser un.",
                                ephemeral=True
                            )
                            return
                        await interaction.response.defer(ephemeral=True)
                        loop_async = asyncio.get_running_loop()
                        try:
                            info = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, url)
                        except Exception as exc:
                            await interaction.followup.send(
                                f"Erreur lors de la récupération d'info : {exc}", ephemeral=True
                            )
                            return
                        play_view = StopPlaybackView(interaction.guild.id, interaction.user.id, timeout=900)
                        loop_msg = " (en boucle)" if loop else ""
                        await interaction.followup.send(
                            f"Lecture de {title} - {url}{loop_msg} lancée dans le salon vocal.\n"
                            "Regardez ce salon pour la barre de progression !",
                            ephemeral=True,
                            view=play_view
                        )
                        asyncio.create_task(
                            play_ytdlp_stream(
                                interaction,
                                info,
                                vc_channel,
                                duration=duration,
                                title=title,
                                video_url=url,
                                announce_message=True,
                                loop=loop,
                                is_live=is_live
                            )
                        )
                        view.stop()

            view = YTSelectLoopView(shown_results)
            sent_msg = await inter.followup.send(content=out_text, view=view, ephemeral=True)
            view.message = sent_msg

        modal = YTSearchModal(on_complete)
        await interaction.response.send_modal(modal)

    @bot.tree.command(
        name="lofi",
        description="Joue un stream lofi chill en boucle dans le vocal"
    )
    @app_commands.describe(
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def lofi(
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel = None
    ):
        LOFI_URL = "https://www.youtube.com/watch?v=aC3K-AqUZyo"  # Lofi Girl 24/7
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop_async = asyncio.get_running_loop()
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        try:
            info = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, LOFI_URL)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors de la récupération d'info : {exc}", ephemeral=True)
            return
        duration = info.get("duration")
        video_title = info.get("title", "Lofi")
        video_url = info.get("webpage_url", LOFI_URL)
        is_live = bool(info.get("is_live")) or info.get("live_status") == "is_live"
        view = StopPlaybackView(interaction.guild.id, interaction.user.id, timeout=900)
        await interaction.followup.send(
            f"Lecture du lofi lancée en boucle dans le salon vocal.\n"
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
                loop=True, # always loop for lofi stream
                is_live=is_live,
            )
        )