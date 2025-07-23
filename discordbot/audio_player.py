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
_progress_tasks = {}

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
    await queue.put((file_path, fut, voice_channel, interaction, False, duration, title, video_url, announce_message, loop, is_live))
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
    # THE FIX: enqueue the YT page URL for loops so that we can re-extract stream URL each time.
    if loop:
        stream_identifier = info_dict.get("webpage_url") or info_dict.get("original_url", info_dict.get("url"))
    else:
        stream_identifier = info_dict.get("url")
        if not stream_identifier:
            for f in reversed(info_dict.get("formats", [])):
                if f.get("acodec") != "none" and f.get("vcodec") == "none":
                    stream_identifier = f.get("url")
                    break
    await queue.put((stream_identifier, fut, voice_channel, interaction, True, duration, title, video_url, announce_message, loop, is_live))
    asyncio.create_task(_run_audio_queue(guild, queue, lock, gid))
    await fut

async def _run_audio_queue(guild, queue, lock, gid):
    # Dispatcher loop: pops & launches playback tasks as needed.
    while True:
        async with lock:
            if queue.empty():
                break
            item = await queue.get()
        # Process the audio OUTSIDE the lock, so event loop never blocks on lock!
        await _process_audio_item(guild, gid, item)

async def _process_audio_item(guild, gid, item):
    from bot_instance import bot
    (
        file_path, fut, voice_channel, interaction,
        use_stream, duration, title, video_url,
        announce_message, loop_flag, is_live
    ) = item
    vc = None
    progress_msg = None
    try:
        # Voice connection logic
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
        # LOOP/AUDIO PLAY LOOP
        while True:
            # For loops on yt-dlp streams, re-extract URL per iteration
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
                    # Update metadata for this repeat loop
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

            start_time = time.time()
            _voice_now_playing[gid] = {
                "vc": vc,
                "start_time": start_time,
                "duration": duration,
                "title": title,
                "url": video_url,
                "message": progress_msg,
                "is_live": is_live,
            }
            if progress_msg:
                _progress_tasks[gid] = asyncio.create_task(_update_progress_message(gid))
            _voice_skip_flag[gid] = False

            # Play audio
            def start_play():
                if not use_stream:
                    return discord.FFmpegPCMAudio(to_play)
                else:
                    return discord.FFmpegPCMAudio(
                        to_play,
                        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                        options="-vn",
                    )
            audio_source = start_play()
            vc.play(audio_source)

            while vc.is_playing():
                if _voice_skip_flag.get(gid, False):
                    vc.stop()
                    break
                await asyncio.sleep(0.5)
            # Clean up after each loop
            t = _progress_tasks.get(gid)
            if t: t.cancel()
            _progress_tasks.pop(gid, None)
            if gid in _voice_now_playing:
                del _voice_now_playing[gid]
            if _voice_skip_flag.get(gid, False):
                break
            if not should_loop:
                break
        # Timeout for disconnect for extra safety
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
    vc = _voice_now_playing.get(gid)
    if vc and isinstance(vc, dict):
        vc = vc.get("vc")
    if vc and vc.is_connected() and vc.is_playing():
        _voice_skip_flag[gid] = True
        return True
    return False

def skip_audio_by_guild(guild_id):
    gid = guild_id
    vc = _voice_now_playing.get(gid)
    if vc and isinstance(vc, dict):
        vc = vc.get("vc")
    if vc and vc.is_connected() and vc.is_playing():
        _voice_skip_flag[gid] = True
        return True
    return False