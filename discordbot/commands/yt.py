import discord
from discord import app_commands
import tempfile
import asyncio
import yt_dlp
from audio_player import play_audio, get_voice_channel, skip_audio_by_guild
from history import log_command
import os

MAX_DURATION = 30 * 60  # 30 minutes in seconds
YTDLP_TIMEOUT = 600     # 10 minutes in seconds

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
        # Call skip_audio_by_guild: this will skip and disconnect the voice client (using your queue logic)
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

async def setup(bot):

    @bot.tree.command(
        name="yt",
        description="Joue l'audio d'une vidéo YouTube dans le vocal"
    )
    @app_commands.describe(
        url="Lien YouTube",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def yt(
        interaction: discord.Interaction,
        url: str,
        voice_channel: discord.VoiceChannel = None
    ):
        log_command(
            interaction.user, "yt",
            {
                "url": url,
                "voice_channel": str(voice_channel) if voice_channel else None
            },
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True, ephemeral=True)
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return
        loop = asyncio.get_running_loop()
        # 1. Check duration FIRST
        try:
            def get_info():
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    return ydl.extract_info(url, download=False)
            info = await asyncio.wait_for(loop.run_in_executor(None, get_info), timeout=60)
            duration = info.get('duration')
            if duration is None:
                raise Exception("Impossible d'obtenir la durée de la vidéo.")
            if duration > MAX_DURATION:
                await interaction.followup.send(
                    f"La vidéo est trop longue (max {MAX_DURATION//60} min) : {duration//60}:{duration%60:02d}.",
                    ephemeral=True
                )
                return
        except Exception as e:
            await interaction.followup.send(f"Erreur lors de l'inspection de la vidéo : {e}", ephemeral=True)
            return
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            filename = tmp.name
        mp3_filename = filename.replace('.webm', '.mp3')
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': filename,
            'quiet': True,
            'noplaylist': True,
            'ffmpeg_location': '/usr/bin',
            'overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        try:
            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            await asyncio.wait_for(loop.run_in_executor(None, download), timeout=YTDLP_TIMEOUT)
            if not os.path.exists(mp3_filename) or os.path.getsize(mp3_filename) == 0:
                await interaction.followup.send("Erreur: le fichier audio téléchargé est vide ou absent.", ephemeral=True)
                return
            asyncio.create_task(play_audio(interaction, mp3_filename, vc_channel))
            view = StopPlaybackView(interaction.guild.id, interaction.user.id)
            await interaction.followup.send(
                "Lecture audio YouTube lancée dans le salon vocal.",
                ephemeral=True,
                view=view
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Téléchargement trop long : essayez une vidéo plus courte.",
                ephemeral=True
            )
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors du téléchargement ou de la lecture : {exc}", ephemeral=True)

    @bot.tree.command(
        name="ytsearch",
        description="Recherche une vidéo YouTube et joue l'audio dans le vocal"
    )
    @app_commands.describe(
        query="Recherche YouTube",
        voice_channel="Salon vocal cible (optionnel)"
    )
    async def ytsearch(
        interaction: discord.Interaction,
        query: str,
        voice_channel: discord.VoiceChannel = None
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop = asyncio.get_running_loop()
        def search():
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                return ydl.extract_info(f"ytsearch5:{query}", download=False)['entries']
        try:
            results = await loop.run_in_executor(None, search)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors de la recherche : {exc}", ephemeral=True)
            return
        if not results:
            await interaction.followup.send("Aucun résultat trouvé.", ephemeral=True)
            return
        results = results[:3]
        msg = "**🎵 Sélectionnez une vidéo à jouer :**\n\n"
        for idx, entry in enumerate(results, 1):
            duration = entry.get('duration')
            duration_str = f" (`{duration//60}:{duration%60:02d}`)" if duration else ""
            uploader = entry.get('uploader', '')
            msg += (
                f"**{idx}.** [{entry['title']}]({entry['webpage_url']})"
                f"{duration_str} — *{uploader}*\n"
            )
        msg += "\n---\nAppuyez sur un bouton ci-dessous pour jouer l'audio."

        class YTButtonView(discord.ui.View):
            def __init__(self, results, timeout=30):
                super().__init__(timeout=timeout)
                for idx, entry in enumerate(results, 1):
                    self.add_item(self.make_button(idx, entry))

            def make_button(self, idx, entry):
                label = f"▶️ {idx}"
                url = entry['webpage_url']
                duration = entry.get('duration')
                async def callback(interaction2: discord.Interaction):
                    await interaction2.response.defer(ephemeral=True)
                    # Check video duration before download!
                    if duration is None:
                        await interaction2.followup.send(
                            "Impossible d'obtenir la durée de la vidéo.",
                            ephemeral=True
                        )
                        return
                    if duration > MAX_DURATION:
                        await interaction2.followup.send(
                            f"La vidéo est trop longue (max {MAX_DURATION//60} min) : {duration//60}:{duration%60:02d}.",
                            ephemeral=True
                        )
                        return
                    log_command(
                        interaction2.user, "ytsearch",
                        {
                            "url": url,
                            "voice_channel": str(voice_channel) if voice_channel else None
                        },
                        guild=interaction2.guild
                    )
                    vc_channel = get_voice_channel(interaction2, voice_channel)
                    if not vc_channel:
                        await interaction2.followup.send(
                            "Vous devez être dans un salon vocal ou en préciser un.",
                            ephemeral=True
                        )
                        return
                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                        filename = tmp.name
                    mp3_filename = filename.replace('.webm', '.mp3')
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': filename,
                        'quiet': True,
                        'noplaylist': True,
                        'ffmpeg_location': '/usr/bin',
                        'overwrites': True,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }],
                    }
                    try:
                        def download():
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                        await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, download), timeout=YTDLP_TIMEOUT)
                        if not os.path.exists(mp3_filename) or os.path.getsize(mp3_filename) == 0:
                            await interaction2.followup.send(
                                "Erreur: le fichier audio téléchargé est vide ou absent.",
                                ephemeral=True
                            )
                            return
                        asyncio.create_task(play_audio(interaction2, mp3_filename, vc_channel))
                        view = StopPlaybackView(interaction2.guild.id, interaction2.user.id)
                        await interaction2.followup.send(
                            f"▶️ Lecture de [{entry['title']}]({url}) lancée dans le salon vocal.",
                            ephemeral=True,
                            view=view
                        )
                    except asyncio.TimeoutError:
                        await interaction2.followup.send(
                            "Téléchargement trop long : essayez une vidéo plus courte.",
                            ephemeral=True
                        )
                    except Exception as exc:
                        await interaction2.followup.send(
                            f"Erreur lors du téléchargement ou de la lecture : {exc}",
                            ephemeral=True
                        )
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.success, custom_id=str(idx))
                button.callback = callback
                return button

        view = YTButtonView(results)
        await interaction.followup.send(msg, view=view, ephemeral=True)
        await view.wait()