# suno.py
import re
import os
import asyncio
import inspect
from typing import Optional, Tuple, Dict

import aiohttp
import discord
from discord import app_commands

from audio_player import play_audio, get_voice_channel, skip_audio_by_guild
from history import log_command


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


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
COMMON_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://suno.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch_text(url: str, timeout: int = 20) -> Tuple[int, str]:
    """Fetch HTML text of a page with headers that mimic a browser."""
    conn_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=conn_timeout, headers=COMMON_HEADERS) as session:
        async with session.get(url, allow_redirects=True) as resp:
            status = resp.status
            text = await resp.text(errors="ignore")
            return status, text


def _extract_meta(html: str, prop: str) -> Optional[str]:
    """Extract content from <meta property="..."> or <meta name="...">."""
    import html as html_unescape
    pattern = re.compile(
        rf'<meta[^>]+(?:property|name)\s*=\s*["\']{re.escape(prop)}["\'][^>]+content\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    m = pattern.search(html)
    if m:
        return html_unescape.unescape(m.group(1)).strip()
    return None


def _extract_first(regexes, html: str) -> Optional[str]:
    for rgx in regexes:
        m = rgx.search(html)
        if m:
            return m.group(1)
    return None


def _unescape_json_like(s: Optional[str]) -> Optional[str]:
    """Unescape common JSON-escaped sequences in inline HTML data."""
    if s is None:
        return s
    out = (
        s.replace("\\/", "/")
         .replace("\\u002F", "/")
         .replace("\\u003A", ":")
         .replace("\\:", ":")
         .replace("\\-", "-")
         .replace("\\.", ".")
         .replace("\\_", "_")
         .replace("\\?", "?")
         .replace("\\&", "&")
         .replace("\\=", "=")
    )
    return out


def extract_suno_info_from_html(html: str) -> Dict[str, Optional[str]]:
    """
    Extract direct audio URL and metadata from a Suno song page.
    Searches for audio_url/audio_url_mp3 fields and OG meta tags.
    """
    audio_patterns = [
        re.compile(r'"audio_url_mp3"\s*:\s*"([^"]+)"'),
        re.compile(r'"audio_url"\s*:\s*"([^"]+)"'),
        re.compile(r'"audio_url"\s*:\s*\[\s*"([^"]+)"'),
    ]
    audio_url = _extract_first(audio_patterns, html)
    if audio_url:
        audio_url = _unescape_json_like(audio_url)

    # Fallback: direct .mp3/.m4a URLs present on the page
    if not audio_url:
        fallback_mp3 = re.findall(r'https?://[^\s"\'<>]+\.mp3', html)
        fallback_m4a = re.findall(r'https?://[^\s"\'<>]+\.m4a', html)
        candidates = [_unescape_json_like(u) for u in (fallback_mp3 + fallback_m4a)]
        # Prefer URLs containing "suno" or "cdn"
        candidates.sort(key=lambda u: ("suno" in u or "cdn" in u, len(u)), reverse=True)
        audio_url = candidates[0] if candidates else None

    title = _extract_meta(html, "og:title") or _extract_meta(html, "twitter:title")
    if not title:
        title = _extract_first([
            re.compile(r'"title"\s*:\s*"([^"]{1,200})"'),
            re.compile(r'"name"\s*:\s*"([^"]{1,200})"'),
        ], html)

    thumbnail = _extract_meta(html, "og:image") or _extract_meta(html, "twitter:image")

    # Optional duration (seconds) if present
    duration = None
    dur_match = re.search(r'"duration"\s*:\s*([0-9]{1,6})', html)
    if dur_match:
        try:
            duration_val = int(dur_match.group(1))
            if 0 < duration_val < 36000:
                duration = duration_val
        except ValueError:
            duration = None

    return {
        "audio_url": audio_url,
        "title": title or "Piste Suno",
        "thumbnail": thumbnail,
        "duration": duration,
    }


async def resolve_suno_audio(url: str) -> Dict[str, Optional[str]]:
    """
    Fetch the Suno song page and extract audio URL + metadata.
    Raises ValueError on failure.
    """
    status, html = await fetch_text(url)
    if status != 200:
        raise ValueError(f"Erreur HTTP {status} en accédant à la page Suno.")

    info = extract_suno_info_from_html(html)
    if not info.get("audio_url"):
        raise ValueError(
            "Impossible d'extraire l'URL audio depuis la page Suno. "
            "La chanson peut être privée, supprimée, ou le format de la page a changé."
        )
    return info


def _guess_ext_from_headers(ct: Optional[str]) -> str:
    if not ct:
        return ".mp3"
    ct = ct.lower()
    if "mpeg" in ct:
        return ".mp3"
    if "mp4" in ct or "m4a" in ct or "aac" in ct:
        return ".m4a"
    if "ogg" in ct or "opus" in ct:
        return ".ogg"
    return ".mp3"


def _guess_ext_from_url(url: str) -> str:
    m = re.search(r'\.([a-zA-Z0-9]{2,5})(?:[?#]|$)', url)
    if not m:
        return ".mp3"
    ext = m.group(1).lower()
    if ext in ("mp3", "m4a", "aac", "ogg", "opus"):
        return "." + ext
    return ".mp3"


async def download_audio_to_temp(audio_url: str) -> str:
    """
    Download the audio file to a temporary path and return the file path.
    The file will be cleaned up by audio_player after playback if it's in temp dir.
    """
    from tempfile import NamedTemporaryFile

    headers = {
        **COMMON_HEADERS,
        "Accept": "*/*",
    }
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(audio_url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise ValueError(f"Téléchargement audio Suno échoué (HTTP {resp.status}).")
            ct = resp.headers.get("Content-Type", "")
            ext = _guess_ext_from_headers(ct) if ct else _guess_ext_from_url(audio_url)
            with NamedTemporaryFile(prefix="suno_", suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name
                try:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        if chunk:
                            tmp.write(chunk)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                except Exception:
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                    raise
    return tmp_path


async def setup(bot):
    @bot.tree.command(
        name="suno",
        description="Lit l'audio d'une chanson Suno dans le salon vocal"
    )
    @app_commands.describe(
        url="Lien vers la chanson Suno (ex: https://suno.com/song/...)",
        voice_channel="Salon vocal cible (optionnel)",
        loop="Lire en boucle (redémarrer quand fini)"
    )
    async def suno(
        interaction: discord.Interaction,
        url: str,
        voice_channel: discord.VoiceChannel = None,
        loop: bool = False
    ):
        log_command(
            interaction.user, "suno",
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

        # Basic validation for Suno domain (UX)
        if "suno.com/song/" not in url:
            await interaction.followup.send(
                "Le lien fourni ne ressemble pas à une URL de chanson Suno valide. "
                "Exemple attendu: https://suno.com/song/<id>?sh=<token>",
                ephemeral=True
            )
            return

        try:
            info = await resolve_suno_audio(url)
        except Exception as exc:
            await interaction.followup.send(f"Erreur lors de l'analyse du lien Suno : {exc}", ephemeral=True)
            return

        audio_url = info["audio_url"]
        title = info.get("title") or "Piste Suno"
        duration = info.get("duration")

        # Download audio locally because play_audio expects a file path
        try:
            tmp_path = await download_audio_to_temp(audio_url)
        except Exception as exc:
            await interaction.followup.send(f"Échec du téléchargement audio Suno : {exc}", ephemeral=True)
            return

        # Inform user and provide a stop button
        view = StopPlaybackView(interaction.guild.id, interaction.user.id, timeout=900)
        loop_msg = " (en boucle)" if loop else ""
        await interaction.followup.send(
            f"Lecture audio Suno{loop_msg} lancée dans le salon vocal.\n"
            "Regardez ce salon pour la barre de progression !",
            ephemeral=True,
            view=view
        )

        # Start playback without blocking the interaction
        asyncio.create_task(
            play_audio(
                interaction,
                tmp_path,
                vc_channel,
                duration=duration,
                title=title,
                video_url=url,
                announce_message=True,
                loop=loop,
                is_live=False
            )
        )