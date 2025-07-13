import discord
import asyncio
import tempfile
import os
import time

_voice_audio_queues = {}
_voice_locks = {}
_voice_now_playing = {}
_voice_skip_flag = {}
_progress_tasks = {}

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
    loop=False,  # <---- ADDED parameter
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
    await queue.put((file_path, fut, voice_channel, interaction, False, duration, title, video_url, announce_message, loop))  # Added loop
    if not lock.locked():
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
    loop=False,  # <---- ADDED parameter
):
    from bot_instance import bot
    stream_url = info_dict.get("url")
    if not stream_url:
        for f in reversed(info_dict.get("formats", [])):
            if f.get("acodec") != "none" and f.get("vcodec") == "none":
                stream_url = f.get("url")
                break
        if not stream_url:
            raise RuntimeError("Aucun flux audio direct trouvé pour la vidéo.")
    guild = interaction.guild
    gid = guild.id if guild else 0
    if gid not in _voice_audio_queues:
        _voice_audio_queues[gid] = asyncio.Queue()
    if gid not in _voice_locks:
        _voice_locks[gid] = asyncio.Lock()
    queue = _voice_audio_queues[gid]
    lock = _voice_locks[gid]
    fut = asyncio.get_event_loop().create_future()
    await queue.put((stream_url, fut, voice_channel, interaction, True, duration, title, video_url, announce_message, loop))  # Added loop
    if not lock.locked():
        asyncio.create_task(_run_audio_queue(guild, queue, lock, gid))
    await fut

async def _run_audio_queue(guild, queue, lock, gid):
    from bot_instance import bot
    async with lock:
        while not queue.empty():
            (
                file_path,
                fut,
                voice_channel,
                interaction,
                use_stream,
                duration,
                title,
                video_url,
                announce_message,
                loop_flag,  # <--- ADDED
            ) = await queue.get()
            try:
                vc = discord.utils.get(bot.voice_clients, guild=guild)
                if not vc or not vc.is_connected():
                    vc = await voice_channel.connect()
                elif vc.channel != voice_channel:
                    await vc.move_to(voice_channel)

                def start_play():
                    if not use_stream:
                        return discord.FFmpegPCMAudio(file_path)
                    else:
                        return discord.FFmpegPCMAudio(
                            file_path,
                            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                            options="-vn",
                        )

                should_loop = loop_flag
                while True:
                    start_time = time.time()
                    progress_msg = None
                    if announce_message:
                        if not title:
                            title = "Audio"
                        msg_txt, bar = _progress_bar(0, duration, title, video_url)
                        progress_msg = await interaction.channel.send(msg_txt)
                    _voice_now_playing[gid] = {
                        "vc": vc,
                        "start_time": start_time,
                        "duration": duration,
                        "title": title,
                        "url": video_url,
                        "message": progress_msg,
                    }
                    if progress_msg:
                        _progress_tasks[gid] = asyncio.create_task(
                            _update_progress_message(gid)
                        )
                    _voice_skip_flag[gid] = False

                    # Play the audio
                    audio_source = start_play()
                    vc.play(audio_source)

                    # Wait for end or skip
                    while vc.is_playing():
                        if _voice_skip_flag.get(gid, False):
                            vc.stop()
                            break
                        await asyncio.sleep(0.5)

                    # If skipping, break loop regardless of loop_flag
                    if _voice_skip_flag.get(gid, False):
                        break

                    # If not looping, break
                    if not should_loop:
                        break

                    # If looping, reset the progress message and play again
                    if progress_msg:
                        try:
                            await progress_msg.delete()
                        except Exception:
                            pass
                    if gid in _voice_now_playing:
                        del _voice_now_playing[gid]
                    t = _progress_tasks.get(gid)
                    if t: t.cancel()
                    _progress_tasks.pop(gid, None)

                await vc.disconnect(force=True)
                if not fut.done():
                    fut.set_result(None)
            except Exception as e:
                if not fut.done():
                    fut.set_exception(e)
            finally:
                if gid in _voice_now_playing:
                    info = _voice_now_playing[gid]
                    msg = info.get("message")
                    if msg:
                        elapsed = int(time.time() - info.get("start_time", time.time()))
                        msg_txt, bar = _progress_bar(
                            elapsed, info.get("duration"), info.get("title"), info.get("url"), ended=True
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
        if not msg: break
        if start is None: break
        elapsed = int(time.time() - start)
        try:
            msg_txt, bar = _progress_bar(
                elapsed, duration, title, video_url
            )
            await msg.edit(content=msg_txt)
        except Exception:
            pass
        await asyncio.sleep(5)

def _progress_bar(elapsed, duration, title, url, ended=False):
    bar_len = 20
    if duration and duration > 0:
        frac = min(1, elapsed / duration)
        filled = int(bar_len * frac)
        bar = "█" * filled + "░" * (bar_len - filled)
        time_total = f"{duration//60}:{duration%60:02d}"
    else:
        frac = 0
        filled = 0
        bar = "░" * bar_len
        time_total = "??:??"
    time_now = f"{elapsed//60}:{elapsed%60:02d}"
    em = "⏹️" if ended else "▶️"
    title_line = f"[{title}]({url})" if url else f"{title}"
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