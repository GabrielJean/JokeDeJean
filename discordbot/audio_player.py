import discord
import asyncio
import tempfile
import os
import time
from concurrent.futures import ProcessPoolExecutor

_voice_audio_queues = {}
_voice_locks = {}
_voice_now_playing = {}
_voice_skip_flag = {}
_voice_seek_flag = {}
_progress_tasks = {}
_voice_queue_running = {}

YTDLP_EXECUTOR = ProcessPoolExecutor(max_workers=6)

def ytdlp_get_info(url):
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True, "format": "bestaudio"}) as ydl:
        return ydl.extract_info(url, download=False)

def get_voice_channel(interaction, specified: discord.VoiceChannel = None):
    if hasattr(interaction.user, "voice") and interaction.user.voice and interaction.user.voice.channel:
        return interaction.user.voice.channel
    elif specified:
        perms = specified.permissions_for(interaction.user)
        if perms.connect and perms.speak:
            return specified
    return None

async def play_audio(
    interaction,
    file_path,
    voice_channel,
    *,
    duration=None,
    title=None,
    video_url=None,
    announce_message=True,
    loop=False,
    is_live=False,
):
    from bot_instance import bot
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found.")
    guild = interaction.guild
    gid = guild.id if guild else 0

    if gid not in _voice_audio_queues:
        _voice_audio_queues[gid] = asyncio.Queue()
    if gid not in _voice_locks:
        _voice_locks[gid] = asyncio.Lock()

    queue = _voice_audio_queues[gid]
    lock = _voice_locks[gid]
    fut = asyncio.get_event_loop().create_future()
    # Note: last param seek_pos is always 0 for play_audio
    await queue.put((file_path, fut, voice_channel, interaction, False, duration, title, video_url, announce_message, loop, is_live, 0))

    if not _voice_queue_running.get(gid):
        _voice_queue_running[gid] = True
        asyncio.create_task(_run_audio_queue(guild, queue, lock, gid))

    await fut

async def play_ytdlp_stream(
    interaction,
    info_dict,
    voice_channel,
    *,
    duration=None,
    title=None,
    video_url=None,
    announce_message=True,
    loop=False,
    is_live=False
):
    from bot_instance import bot
    guild = interaction.guild
    gid = guild.id if guild else 0

    if gid not in _voice_audio_queues:
        _voice_audio_queues[gid] = asyncio.Queue()
    if gid not in _voice_locks:
        _voice_locks[gid] = asyncio.Lock()

    queue = _voice_audio_queues[gid]
    lock = _voice_locks[gid]
    fut = asyncio.get_event_loop().create_future()
    # Note: last param seek_pos is always 0 for fresh play
    if loop:
        stream_identifier = info_dict.get("webpage_url") or info_dict.get("original_url", info_dict.get("url"))
    else:
        stream_identifier = info_dict.get("url")
        if not stream_identifier:
            for f in reversed(info_dict.get("formats", [])):
                if f.get("acodec") != "none" and f.get("vcodec") == "none":
                    stream_identifier = f.get("url")
                    break
    await queue.put((stream_identifier, fut, voice_channel, interaction, True, duration, title, video_url, announce_message, loop, is_live, 0))

    if not _voice_queue_running.get(gid):
        _voice_queue_running[gid] = True
        asyncio.create_task(_run_audio_queue(guild, queue, lock, gid))

    await fut

async def _run_audio_queue(guild, queue, lock, gid):
    try:
        while True:
            async with lock:
                if queue.empty():
                    break
                item = await queue.get()
            await _process_audio_item(guild, gid, item)
    finally:
        _voice_queue_running[gid] = False

async def _process_audio_item(guild, gid, item):
    from bot_instance import bot
    (
        file_path, fut, voice_channel, interaction,
        use_stream, duration, title, video_url,
        announce_message, loop_flag, is_live, seek_pos
    ) = item
    vc = None
    progress_msg = None
    try:
        vc = discord.utils.get(bot.voice_clients, guild=guild)
        if not vc or not vc.is_connected():
            vc = await voice_channel.connect()
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        should_loop = loop_flag
        if announce_message:
            disp_title = title or "Audio"
            msg_txt, bar = _progress_bar(0, duration, disp_title, video_url, is_live=is_live)
            progress_msg = await interaction.channel.send(msg_txt)

        loop_async = asyncio.get_running_loop()
        base_seek = seek_pos
        while True:
            # yt-dlp url re-extraction for looping
            if use_stream and should_loop:
                url_to_play = file_path
                try:
                    info_dict = await loop_async.run_in_executor(
                        YTDLP_EXECUTOR, ytdlp_get_info, url_to_play
                    )
                    stream_url = info_dict.get("url")
                    if not stream_url:
                        for f in reversed(info_dict.get("formats", [])):
                            if f.get("acodec") != "none" and f.get("vcodec") == "none":
                                stream_url = f.get("url")
                                break
                    if not stream_url:
                        raise RuntimeError("Aucun flux audio direct trouvé pour la vidéo (loop).")
                    if info_dict.get("title"): title = info_dict.get("title", title)
                    if info_dict.get("duration"): duration = info_dict.get("duration", duration)
                    video_url = info_dict.get("webpage_url", video_url)
                    is_live = bool(info_dict.get("is_live")) or info_dict.get("live_status") == "is_live"
                    to_play = stream_url
                except Exception as exc:
                    if not fut.done():
                        fut.set_exception(exc)
                    break
            else:
                to_play = file_path

            seek_offset = base_seek or 0
            base_seek = 0  # only for first play/seek
            _voice_now_playing[gid] = {
                "vc": vc,
                "start_time": time.time() - seek_offset,
                "duration": duration,
                "title": title,
                "url": video_url,
                "message": progress_msg,
                "is_live": is_live,
                "offset": seek_offset,
                "playing_file_path": to_play,
                "use_stream": use_stream,
                "loop_flag": loop_flag
            }
            if progress_msg:
                _progress_tasks[gid] = asyncio.create_task(_update_progress_message(gid))
            _voice_skip_flag[gid] = False
            _voice_seek_flag[gid] = 0

            # Make sure not to double play
            if vc.is_playing():
                vc.stop()
                for _ in range(20):
                    if not vc.is_playing():
                        break
                    await asyncio.sleep(0.1)

            def start_play():
                # --- SEEK support via -ss for ffmpeg ---
                offset = seek_offset or 0
                ss = f"-ss {offset}" if offset > 0 else ""
                if not use_stream:
                    return discord.FFmpegPCMAudio(
                        to_play,
                        before_options=ss,
                    )
                else:
                    return discord.FFmpegPCMAudio(
                        to_play,
                        before_options=f"{ss} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5".strip(),
                        options="-vn",
                    )
            audio_source = start_play()
            try:
                vc.play(audio_source)
            except discord.errors.ClientException as e:
                if not fut.done():
                    fut.set_exception(e)
                break

            # --- Playback/Skip/Seek loop ---
            while vc.is_connected():
                # Always break if we're skipping or finished
                if _voice_skip_flag.get(gid, False):
                    if vc.is_playing():
                        vc.stop()
                    break
                seek_jump = _voice_seek_flag.get(gid, 0)
                if seek_jump:
                    elapsed = int(time.time() - _voice_now_playing[gid]["start_time"]) + seek_jump
                    if duration:
                        elapsed = max(0, min(elapsed, duration-1))
                    _voice_seek_flag[gid] = 0
                    await _voice_audio_queues[gid].put(
                        (file_path, fut, voice_channel, interaction, use_stream, duration, title, video_url, announce_message, loop_flag, is_live, elapsed)
                    )
                    if vc.is_playing():
                        vc.stop()
                    return
                if not vc.is_playing():
                    break
                await asyncio.sleep(0.5)

            t = _progress_tasks.get(gid)
            if t: t.cancel()
            _progress_tasks.pop(gid, None)
            if gid in _voice_now_playing:
                del _voice_now_playing[gid]
            if _voice_skip_flag.get(gid, False):
                break
            if not should_loop:
                break
        try:
            await asyncio.wait_for(vc.disconnect(force=True), timeout=10)
        except asyncio.TimeoutError:
            pass
        if not fut.done():
            fut.set_result(None)
    except Exception as e:
        if not fut.done():
            fut.set_exception(e)
    finally:
        if gid in _voice_now_playing:
            info = _voice_now_playing[gid]
            msg = info.get("message")
            is_live = info.get("is_live", False)
            if msg:
                elapsed = int(time.time() - info.get("start_time", time.time()))
                msg_txt, bar = _progress_bar(
                    elapsed, info.get("duration"), info.get("title"), info.get("url"), ended=True, is_live=is_live
                )
                try:
                    asyncio.create_task(msg.edit(content=msg_txt))
                except Exception:
                    pass
            del _voice_now_playing[gid]
        _voice_skip_flag[gid] = False
        _voice_seek_flag[gid] = 0
        t = _progress_tasks.get(gid)
        if t: t.cancel()
        _progress_tasks.pop(gid, None)
        try:
            if not use_stream and file_path.startswith(tempfile.gettempdir()) and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as ex:
            print(f"Audio cleanup warning: {ex}")

async def _update_progress_message(gid):
    while True:
        info = _voice_now_playing.get(gid)
        if not info: break
        msg = info.get("message")
        duration = info.get("duration")
        start = info.get("start_time")
        title = info.get("title")
        video_url = info.get("url")
        is_live = info.get("is_live", False)
        if not msg or start is None:
            break
        elapsed = int(time.time() - start)
        try:
            msg_txt, bar = _progress_bar(
                elapsed, duration, title, video_url, is_live=is_live
            )
            await msg.edit(content=msg_txt)
        except Exception:
            pass
        await asyncio.sleep(5)

def _progress_bar(elapsed, duration, title, url, ended=False, is_live=False):
    bar_len = 20
    em = "⏹️" if ended else "▶️"
    title_line = f"{title} {url}" if url else f"{title}"
    if is_live:
        bar = "🔴 LIVE".center(bar_len)
        msg = f"{title_line}\n🔴 {bar} — EN DIRECT"
        return msg, bar
    if duration and duration > 0:
        frac = min(1, elapsed / duration)
        filled = int(bar_len * frac)
        bar = "█" * filled + "░" * (bar_len - filled)
        time_total = f"{duration//60}:{duration%60:02d}"
    else:
        bar = "░" * bar_len
        time_total = "??:??"
    time_now = f"{elapsed//60}:{elapsed%60:02d}"
    msg = f"{title_line}\n{em} {bar} `{time_now} / {time_total}`"
    return msg, bar

def skip_audio(voice_channel: discord.VoiceChannel):
    gid = voice_channel.guild.id if voice_channel else None
    if gid is None:
        return False
    info = _voice_now_playing.get(gid)
    if info and isinstance(info, dict):
        vc = info.get("vc")
        if vc and vc.is_connected():
            _voice_skip_flag[gid] = True
            return True
    return False

def skip_audio_by_guild(guild_id):
    gid = guild_id
    info = _voice_now_playing.get(gid)
    if info and isinstance(info, dict):
        vc = info.get("vc")
        if vc and vc.is_connected():
            _voice_skip_flag[gid] = True
            return True
    return False

def seek_audio_by_guild(guild_id, seconds: int):
    """Request player to seek by +seconds (forward) or -seconds (rewind), returns new position or None if not possible."""
    info = _voice_now_playing.get(guild_id)
    if not info or info.get("is_live") or not info.get("duration"):
        return None  # Cannot seek if nothing is playing, or live, or unknown duration
    now = int(time.time() - info["start_time"]) + (info.get('offset') or 0)
    new_pos = max(0, min(now + seconds, info["duration"] - 1))
    _voice_seek_flag[guild_id] = new_pos - now
    return new_pos