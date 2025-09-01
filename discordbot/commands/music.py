import discord
from discord import app_commands
import asyncio
import yt_dlp
import random
import json
from pathlib import Path
from audio_player import play_ytdlp_stream, get_voice_channel, consume_rotation_stop, skip_audio_by_guild
from history import log_command
from concurrent.futures import ProcessPoolExecutor

YTDLP_EXECUTOR = ProcessPoolExecutor(max_workers=6)

YTDLP_CLIENT_ORDER = ["android", "ios", "web"]

# Path to the JSON file defining categories and URLs
MUSIC_SOURCES_PATH = (Path(__file__).resolve().parent.parent / "music_sources.json")


def load_music_sources():
    try:
        with open(MUSIC_SOURCES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        normalized = {}
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, list):
                continue
            urls = [u.strip() for u in v if isinstance(u, str) and u.strip()]
            normalized[k] = urls
        return normalized
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

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
    async def music(
        interaction: discord.Interaction,
        category: str = None,
        voice_channel: discord.VoiceChannel = None
    ):
        cat = category.strip().lower() if isinstance(category, str) and category else None
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
            categories_map = load_music_sources()
            if not categories_map:
                await interaction.followup.send("Aucune catégorie disponible. Configurez d'abord music_sources.json.", ephemeral=True)
                return
            class CategorySelectView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=120)
                    self.selected_key = None
                    options = []
                    for key in categories_map.keys():
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
                        categories_map_local = load_music_sources()
                        sources = categories_map_local.get(cat_key, [])
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

        categories_map = load_music_sources()
        if cat and cat not in categories_map:
            await interaction.followup.send("Catégorie inconnue. Veuillez choisir parmi: " + ", ".join(sorted(k.replace('_',' ') for k in categories_map.keys())), ephemeral=True)
            return
        sources = categories_map.get(cat, [])
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
        cat_display = (cat or "").replace('_', ' ') or "(non spécifiée)"
        await interaction.followup.send(
            f"Lecture de musique '{cat_display}' démarrée — regardez l'annonce du player dans le salon.",
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

