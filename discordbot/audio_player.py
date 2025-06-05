import discord
import asyncio
import tempfile
import os

_voice_audio_queues = {}
_voice_locks = {}
_voice_now_playing = {}
_voice_skip_flag = {}

def get_voice_channel(interaction, specified: discord.VoiceChannel = None):
    if hasattr(interaction.user, "voice") and interaction.user.voice and interaction.user.voice.channel:
        return interaction.user.voice.channel
    elif specified:
        perms = specified.permissions_for(interaction.user)
        if perms.connect and perms.speak:
            return specified
    return None

async def play_audio(interaction, file_path, voice_channel):
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
    await queue.put((file_path, fut, voice_channel, interaction))
    if not lock.locked():
        asyncio.create_task(_run_audio_queue(guild, queue, lock, gid))
    await fut

async def _run_audio_queue(guild, queue, lock, gid):
    from bot_instance import bot
    async with lock:
        while not queue.empty():
            file_path, fut, voice_channel, interaction = await queue.get()
            try:
                vc = discord.utils.get(bot.voice_clients, guild=guild)
                if not vc or not vc.is_connected():
                    vc = await voice_channel.connect()
                elif vc.channel != voice_channel:
                    await vc.move_to(voice_channel)

                _voice_now_playing[gid] = vc
                _voice_skip_flag[gid] = False

                vc.play(discord.FFmpegPCMAudio(file_path))

                # Wait for current file to finish or skip
                while vc.is_playing():
                    if _voice_skip_flag.get(gid, False):
                        vc.stop()
                        break
                    await asyncio.sleep(0.5)

                await vc.disconnect(force=True)
                if not fut.done():
                    fut.set_result(None)
            except Exception as e:
                if not fut.done():
                    fut.set_exception(e)
            finally:
                if gid in _voice_now_playing:
                    del _voice_now_playing[gid]
                _voice_skip_flag[gid] = False
                try:
                    if file_path.startswith(tempfile.gettempdir()) and os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as ex:
                    print(f"Audio cleanup warning: {ex}")

def skip_audio(voice_channel: discord.VoiceChannel):
    """Skip current playing audio in the guild for the specified channel."""
    gid = voice_channel.guild.id if voice_channel else None
    if gid is None:
        return False
    # If there is an ongoing playback:
    vc = _voice_now_playing.get(gid)
    if vc and vc.is_connected() and vc.is_playing():
        # Set skip flag and disconnect will happen in the queue loop
        _voice_skip_flag[gid] = True
        return True
    return False