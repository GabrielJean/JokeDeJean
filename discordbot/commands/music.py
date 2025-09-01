import discord
from discord import app_commands
import asyncio
import yt_dlp
import random
from audio_player import play_ytdlp_stream, get_voice_channel, consume_rotation_stop, skip_audio_by_guild
from history import log_command
from concurrent.futures import ProcessPoolExecutor

YTDLP_EXECUTOR = ProcessPoolExecutor(max_workers=6)

YTDLP_CLIENT_ORDER = ["android", "ios", "web"]

# Curated categories with YouTube sources (videos or playlists).
# Replace the example URLs with your own.
MUSIC_SOURCES = {
    "lofi": [
        "https://www.youtube.com/watch?v=GU8htjxY6ro",
        "https://www.youtube.com/watch?v=BfPZp30enLc",
        "https://www.youtube.com/watch?v=CkntZ7ijS2s",
        "https://www.youtube.com/watch?v=aC3K-AqUZyo",
        "https://www.youtube.com/watch?v=Yqk13qPcXis",
        # Add more lofi playlists/videos
    ],
    "gaming": [
        "https://www.youtube.com/watch?v=PP2Uvesx4ls",
        "https://www.youtube.com/watch?v=ZdU6qDeMM_I",
        "https://www.youtube.com/watch?v=B7QzbCViK0E",
        "https://www.youtube.com/watch?v=_6nv4rrIMuU",
        "https://www.youtube.com/watch?v=5bUa1w24ASc",
        "https://www.youtube.com/watch?v=FqwsbV5hItg"
    ],
    "hype": [
        "https://www.youtube.com/watch?v=5bUa1w24ASc",
    ],
    "chill": [
        # Add chill playlists/videos
    ],
    "rock": [
        "https://www.youtube.com/watch?v=V5jZirHBGCs",
        "https://www.youtube.com/watch?v=4Rr4Cv2TsU8",
        "https://www.youtube.com/watch?v=eh87FoETejw",
    ],
    "classical_music": [
        "https://www.youtube.com/watch?v=t0CdR6LximA",
        "https://www.youtube.com/watch?v=ElWSdcg67RY",
    ],
    "ost_anime": [
        "https://www.youtube.com/watch?v=GNWLILeztaI",
        "https://www.youtube.com/watch?v=RFi98VZETm0",
        "https://www.youtube.com/watch?v=4N9HmMNf7EU"
        "https://www.youtube.com/watch?v=zavCTwkGseg"
        "https://www.youtube.com/watch?v=JdU0gDDCiB8"
    ],
    "jazz/blues": [
        "https://www.youtube.com/watch?v=eh87FoETejw"
        "https://www.youtube.com/watch?v=L1xwUKxpdJg"
        "https://www.youtube.com/watch?v=qclDEAj7SAU"
        "https://www.youtube.com/watch?v=T4O0j-pjHA8"
        "https://www.youtube.com/watch?v=6fxxghNzKmM"
    ],
}

# Per-guild stop flags for the music rotation task (internal control)
_MUSIC_ROTATION_STOP_FLAGS = {}


def _make_ydl_opts(client: str):
    return {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'format': 'bestaudio/best',
        'extractor_args': {
            # Workaround for YouTube SABR streaming blocking some web formats
            'youtube': {
                'player_client': [client]
            }
        },
    }


def _make_playlist_opts(client: str):
    # Options to expand playlist entries without downloading media
    base = _make_ydl_opts(client).copy()
    base['noplaylist'] = False
    base['extract_flat'] = 'in_playlist'
    base['skip_download'] = True
    return base


def ytdlp_get_info(url):
    last_exc = None
    for client in YTDLP_CLIENT_ORDER:
        try:
            with yt_dlp.YoutubeDL(_make_ydl_opts(client)) as ydl:
                info = ydl.extract_info(url, download=False)
                info['__client'] = client
                return info
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc


def ytdlp_expand_to_videos(url):
    """Return a list of YouTube video webpage URLs for a given video or playlist URL."""
    last_exc = None
    for client in YTDLP_CLIENT_ORDER:
        try:
            with yt_dlp.YoutubeDL(_make_playlist_opts(client)) as ydl:
                info = ydl.extract_info(url, download=False)
                # If it's a playlist, info will typically have 'entries'
                if isinstance(info, dict) and info.get('entries'):
                    out = []
                    for e in info['entries']:
                        wp = e.get('webpage_url') or e.get('url')
                        if wp and not str(wp).startswith('http'):
                            wp = f"https://www.youtube.com/watch?v={wp}"
                        if wp:
                            out.append(wp)
                    if out:
                        return out
                # Single video fallback
                wp = info.get('webpage_url', url) if isinstance(info, dict) else url
                return [wp]
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc


async def setup(bot):
    @bot.tree.command(
        name="music",
        description="Joue une catégorie de musique YouTube en rotation aléatoire"
    )
    @app_commands.describe(
        category="Catégorie de musique",
        voice_channel="Salon vocal cible (optionnel)"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="lofi", value="lofi"),
            app_commands.Choice(name="gaming", value="gaming"),
            app_commands.Choice(name="hype", value="hype"),
            app_commands.Choice(name="chill", value="chill"),
            app_commands.Choice(name="rock", value="rock"),
            app_commands.Choice(name="classical music", value="classical_music"),
            app_commands.Choice(name="ost anime", value="ost_anime"),
            app_commands.Choice(name="jazz/blues", value="jazz/blues"),
        ]
    )
    async def music(
        interaction: discord.Interaction,
        category: app_commands.Choice[str] = None,
        voice_channel: discord.VoiceChannel = None
    ):
        cat = category.value if isinstance(category, app_commands.Choice) else str(category)
        log_command(
            interaction.user, "music",
            {"category": cat, "voice_channel": str(voice_channel) if voice_channel else None},
            guild=interaction.guild
        )
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop_async = asyncio.get_running_loop()
        vc_channel = get_voice_channel(interaction, voice_channel)
        if not vc_channel:
            await interaction.followup.send("Vous devez être dans un salon vocal ou en préciser un.", ephemeral=True)
            return

        # If no category provided, show a UI to select it, then start rotation
        if category is None:
            class CategorySelectView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=120)
                    self.selected_key = None
                    options = []
                    for key in MUSIC_SOURCES.keys():
                        nice = key.replace('_', ' ')
                        options.append(discord.SelectOption(label=nice, value=key))
                    self.select = discord.ui.Select(placeholder="Choisissez une catégorie...", min_values=1, max_values=1, options=options)

                    async def on_select(inter: discord.Interaction):
                        self.selected_key = self.select.values[0]
                        await inter.response.defer()

                    self.select.callback = on_select
                    self.add_item(self.select)

                    self.confirm = discord.ui.Button(label="Confirmer", style=discord.ButtonStyle.success)

                    async def on_confirm(inter: discord.Interaction):
                        if not self.selected_key:
                            await inter.response.send_message("Sélectionnez une catégorie.", ephemeral=True)
                            return
                        await inter.response.defer(ephemeral=True)
                        cat_key = self.selected_key
                        sources = MUSIC_SOURCES.get(cat_key, [])
                        if not sources:
                            await inter.followup.send("Aucune source configurée pour cette catégorie.", ephemeral=True)
                            return
                        gid = inter.guild.id if inter.guild else 0
                        if _MUSIC_ROTATION_STOP_FLAGS.get(gid) is False:
                            _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                            skip_audio_by_guild(gid)
                            await asyncio.sleep(0.5)
                        _MUSIC_ROTATION_STOP_FLAGS[gid] = False
                        await inter.followup.send(
                            f"Lecture de musique '{cat_key.replace('_',' ')}' démarrée",
                            ephemeral=True,
                        )
                        loop_async_local = asyncio.get_running_loop()

                        async def rotation_task():
                            expanded = []
                            for src in sources:
                                try:
                                    lst = await loop_async_local.run_in_executor(YTDLP_EXECUTOR, ytdlp_expand_to_videos, src)
                                    expanded.extend(lst)
                                except Exception:
                                    continue
                            seen = set()
                            expanded = [x for x in expanded if not (x in seen or seen.add(x))]
                            if not expanded:
                                await inter.followup.send("Aucune source valide trouvée pour cette catégorie.", ephemeral=True)
                                _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                                return
                            last_url = None
                            first_announce = True
                            while not _MUSIC_ROTATION_STOP_FLAGS.get(gid, False):
                                order = expanded[:]
                                random.shuffle(order)
                                if last_url and len(order) > 1 and order[0] == last_url:
                                    for i in range(1, len(order)):
                                        if order[i] != last_url:
                                            order[0], order[i] = order[i], order[0]
                                            break
                                for url in order:
                                    if _MUSIC_ROTATION_STOP_FLAGS.get(gid, False):
                                        break
                                    try:
                                        info = await loop_async_local.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, url)
                                    except Exception:
                                        last_url = url
                                        continue
                                    duration = info.get("duration")
                                    video_title = info.get("title", "Musique")
                                    video_url = info.get("webpage_url", url)
                                    is_live = bool(info.get("is_live")) or info.get("live_status") == "is_live"
                                    try:
                                        await play_ytdlp_stream(
                                            inter,
                                            info,
                                            vc_channel,
                                            duration=duration,
                                            title=video_title,
                                            video_url=video_url,
                                            announce_message=first_announce,
                                            loop=False,
                                            is_live=is_live,
                                        )
                                    except Exception:
                                        pass
                                    first_announce = False
                                    last_url = url
                                    if consume_rotation_stop(gid):
                                        _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                                        break
                            _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                        asyncio.create_task(rotation_task())
                        self.stop()

                    self.confirm.callback = on_confirm
                    self.add_item(self.confirm)

            view = CategorySelectView()
            await interaction.followup.send("Choisissez une catégorie de musique:", view=view, ephemeral=True)
            return

        sources = MUSIC_SOURCES.get(cat, [])
        if not sources:
            await interaction.followup.send("Aucune source configurée pour cette catégorie.", ephemeral=True)
            return

        gid = interaction.guild.id if interaction.guild else 0
        # Stop any existing rotation in this guild
        if _MUSIC_ROTATION_STOP_FLAGS.get(gid) is False:
            _MUSIC_ROTATION_STOP_FLAGS[gid] = True
            skip_audio_by_guild(gid)
            await asyncio.sleep(0.5)
        _MUSIC_ROTATION_STOP_FLAGS[gid] = False

        # Accusé de réception minimal; l'annonce du player gère les boutons Stop/Skip
        await interaction.followup.send(
            f"Lecture de musique '{category.name}' démarrée",
            ephemeral=True,
        )

        async def rotation_task():
            # Expand all sources into a flat list of video URLs
            expanded = []
            for src in sources:
                try:
                    lst = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_expand_to_videos, src)
                    expanded.extend(lst)
                except Exception:
                    continue
            # Deduplicate preserving order
            seen = set()
            expanded = [x for x in expanded if not (x in seen or seen.add(x))]
            if not expanded:
                await interaction.followup.send("Aucune source valide trouvée pour cette catégorie.", ephemeral=True)
                _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                return

            last_url = None
            first_announce = True
            while not _MUSIC_ROTATION_STOP_FLAGS.get(gid, False):
                order = expanded[:]
                random.shuffle(order)
                # Avoid repeating the same URL across boundaries
                if last_url and len(order) > 1 and order[0] == last_url:
                    for i in range(1, len(order)):
                        if order[i] != last_url:
                            order[0], order[i] = order[i], order[0]
                            break
                for url in order:
                    if _MUSIC_ROTATION_STOP_FLAGS.get(gid, False):
                        break
                    try:
                        info = await loop_async.run_in_executor(YTDLP_EXECUTOR, ytdlp_get_info, url)
                    except Exception:
                        last_url = url
                        continue
                    duration = info.get("duration")
                    video_title = info.get("title", "Musique")
                    video_url = info.get("webpage_url", url)
                    is_live = bool(info.get("is_live")) or info.get("live_status") == "is_live"
                    try:
                        await play_ytdlp_stream(
                            interaction,
                            info,
                            vc_channel,
                            duration=duration,
                            title=video_title,
                            video_url=video_url,
                            announce_message=first_announce,
                            loop=False,
                            is_live=is_live,
                        )
                    except Exception:
                        pass
                    first_announce = False
                    last_url = url
                    # Si le bouton Stop du player a été pressé, sort de la rotation
                    if consume_rotation_stop(gid):
                        _MUSIC_ROTATION_STOP_FLAGS[gid] = True
                        break
            _MUSIC_ROTATION_STOP_FLAGS[gid] = True

        asyncio.create_task(rotation_task())

