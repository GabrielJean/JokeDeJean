import asyncio
import base64
import json
import logging
import re
import wave
from typing import Optional
import websockets
try:
    import edge_tts  # type: ignore
except Exception:  # pragma: no cover
    edge_tts = None  # type: ignore

"""TTS utility helper for xAI Voice Agent (WebSocket realtime) only.

Uses the config accessor from bot_instance. Supports both package execution
(python -m discordbot.main) and direct script execution by providing a
relative-first then absolute import fallback for get_config.
"""
try:  # Package relative import (python -m discordbot.main)
    from .bot_instance import get_config  # type: ignore
except Exception:  # pragma: no cover - fallback when run as script
    try:
        from bot_instance import get_config  # type: ignore
    except Exception:  # Final fallback – define a stub to avoid crash
        def get_config():  # type: ignore
            return {}

_VALID_VOICES = {"Ara", "Rex", "Sal", "Eve", "Leo"}

def _normalize_voice(voice: Optional[str]) -> str:
    if not voice:
        return "Ara"
    # normalize common lower-case names
    normalized = voice.strip().title()
    if normalized in _VALID_VOICES:
        return normalized
    return "Ara"


async def _run_voice_agent_tts(text: str, instructions: str, voice: str, sample_rate: int) -> tuple[bytes, str]:
    cfg = get_config()
    api_key = cfg.get("xai_api_key")
    if not api_key:
        raise RuntimeError("Missing xAI API key (xai_api_key).")

    base_url = "wss://api.x.ai/v1/realtime"
    audio_chunks: list[bytes] = []
    text_chunks: list[str] = []

    async with websockets.connect(
        uri=base_url,
        ssl=True,
        additional_headers={"Authorization": f"Bearer {api_key}"},
    ) as ws:
        # Configure session
        session_config = {
            "type": "session.update",
            "session": {
                "voice": voice,
                "instructions": instructions or "",
                "turn_detection": {"type": None},
                "audio": {
                    "output": {"format": {"type": "audio/pcm", "rate": sample_rate}},
                },
            },
        }
        await ws.send(json.dumps(session_config))

        # Send user text
        user_msg = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
        await ws.send(json.dumps(user_msg))

        # Request response with audio
        verbatim_instruction = (
            "Lis le dernier message utilisateur mot pour mot, sans rien ajouter, "
            "retirer, reformuler ni traduire. Respecte la ponctuation et l'ordre des mots."
        )
        merged_instructions = (instructions or "").strip()
        if merged_instructions:
            merged_instructions = f"{merged_instructions}\n{verbatim_instruction}"
        else:
            merged_instructions = verbatim_instruction
        response_req = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": merged_instructions,
            },
        }
        await ws.send(json.dumps(response_req))

        # Read stream
        while True:
            raw = await ws.recv()
            event = json.loads(raw)
            etype = event.get("type")
            if etype == "response.output_audio.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    audio_chunks.append(base64.b64decode(delta))
            elif etype == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    text_chunks.append(delta)
            elif etype == "response.output_audio.done":
                break
            elif etype == "response.done":
                # In case output_audio.done was skipped
                break

    return b"".join(audio_chunks), "".join(text_chunks).strip()


async def _run_voice_agent_generation(
    user_prompt: str,
    system_prompt: str,
    delivery_instructions: str,
    voice: str,
    sample_rate: int,
) -> tuple[bytes, str]:
    cfg = get_config()
    api_key = cfg.get("xai_api_key")
    if not api_key:
        raise RuntimeError("Missing xAI API key (xai_api_key).")

    base_url = "wss://api.x.ai/v1/realtime"
    audio_chunks: list[bytes] = []
    text_chunks: list[str] = []

    session_instructions = (system_prompt or "").strip()
    if delivery_instructions:
        session_instructions = f"{session_instructions}\n\n{delivery_instructions}".strip()

    async with websockets.connect(
        uri=base_url,
        ssl=True,
        additional_headers={"Authorization": f"Bearer {api_key}"},
    ) as ws:
        session_config = {
            "type": "session.update",
            "session": {
                "voice": voice,
                "instructions": session_instructions,
                "turn_detection": {"type": None},
                "audio": {
                    "output": {"format": {"type": "audio/pcm", "rate": sample_rate}},
                },
            },
        }
        await ws.send(json.dumps(session_config))

        user_msg = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        }
        await ws.send(json.dumps(user_msg))

        response_req = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
            },
        }
        await ws.send(json.dumps(response_req))

        while True:
            raw = await ws.recv()
            event = json.loads(raw)
            etype = event.get("type")
            if etype == "response.output_audio.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    audio_chunks.append(base64.b64decode(delta))
            elif etype == "response.output_audio_transcript.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    text_chunks.append(delta)
            elif etype == "response.done":
                break

    return b"".join(audio_chunks), "".join(text_chunks).strip()


async def _run_voice_agent_verbatim_tts(
    text: str,
    delivery_instructions: str,
    voice: str,
    sample_rate: int,
) -> bytes:
    cfg = get_config()
    api_key = cfg.get("xai_api_key")
    if not api_key:
        raise RuntimeError("Missing xAI API key (xai_api_key).")

    base_url = "wss://api.x.ai/v1/realtime"
    audio_chunks: list[bytes] = []

    style_block = (delivery_instructions or "").strip()
    session_instructions = (
        "You are a TTS engine for Discord. Keep latency low and produce natural speech. "
        "Any style instructions only affect delivery/prosody and accent, never wording."
    )
    if style_block:
        session_instructions = f"{session_instructions}\n\nDelivery style: {style_block}"

    response_instructions = (
        "Read the last user message EXACTLY verbatim. "
        "Do not add, remove, censor, summarize, translate, or rephrase anything. "
        "Keep punctuation and word order exactly as provided."
    )

    async with websockets.connect(
        uri=base_url,
        ssl=True,
        additional_headers={"Authorization": f"Bearer {api_key}"},
    ) as ws:
        session_config = {
            "type": "session.update",
            "session": {
                "voice": voice,
                "instructions": session_instructions,
                "turn_detection": {"type": None},
                "audio": {
                    "output": {"format": {"type": "audio/pcm", "rate": sample_rate}},
                },
            },
        }
        await ws.send(json.dumps(session_config))

        user_msg = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
        await ws.send(json.dumps(user_msg))

        response_req = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
                "instructions": response_instructions,
            },
        }
        await ws.send(json.dumps(response_req))

        while True:
            raw = await ws.recv()
            event = json.loads(raw)
            etype = event.get("type")
            if etype == "response.output_audio.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    audio_chunks.append(base64.b64decode(delta))
            elif etype == "response.output_audio.done":
                break
            elif etype == "response.done":
                break

    return b"".join(audio_chunks)


async def _run_edge_tts(text: str, voice: str, filename: str) -> None:
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(filename)


def _detect_refusal(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    patterns = [
        "can't answer",
        "cannot answer",
        "can't comply",
        "cannot comply",
        "can't help",
        "cannot help",
        "i can't",
        "i cannot",
        "je ne peux pas",
        "je peux pas",
        "désolé",
        "refuse",
    ]
    return any(p in lowered for p in patterns)


def quebecify_text(text: str) -> str:
    """Transform text to be pronounced with a strong Beauce-style Quebec accent.

    Applies intense phonetic transformations for a stereotypical Beauce accent.
    """
    # Transformations phonétiques beauceronnes (accent très prononcé)
    transformations = [
        # DIPHTONGUES BEAUCERONNES EXTRÊMES
        (r'\bmoi\b', 'moué'),         # moi -> moué
        (r'\btoi\b', 'toué'),         # toi -> toué
        (r'\bpoi', 'poué'),           # poids -> pouéds
        (r'oi([^nrs])', r'oué\1'),    # noir -> nouér
        (r'oir\b', 'ouére'),          # voir -> vouére
        (r'ois\b', 'oué'),            # fois -> foué

        # ASSIBILATION FORTE (très caractéristique de la Beauce)
        (r't([iu])', r'tss\1'),       # tu -> tssou, ti -> tsssi (encore plus appuyé)
        (r'd([iu])', r'dzz\1'),       # du -> dzzou, di -> dzzzi
        (r'T([iu])', r'TSS\1'),       # Majuscule aussi
        (r'D([iu])', r'DZZ\1'),

        # VOYELLES ALLONGÉES ET NASALES (très beauceronnes)
        (r'â', 'âââ'),                # pâte -> pâââte
        (r'ê', 'êêêê'),               # être -> êêêtre
        (r'in\b', 'aiiinnng'),        # vin -> vaiiinnng (nasalisation extrême)
        (r'ain\b', 'aiiinnng'),       # pain -> paiiinnng
        (r'an\b', 'annng'),           # avant -> avannng
        (r'en\b', 'annng'),           # bien -> biannng

        # ÉLISIONS ET CONTRACTIONS BEAUCERONNES
        (r'\bje suis\b', 'chu'),      # je suis -> chu
        (r'\bje\b', 'j'),             # je -> j
        (r'\bne\b', 'n'),             # ne -> n
        (r'\bce\b', 'c'),             # ce -> c
        (r'\bde\b', 'd'),             # de -> d
        (r'\bil est\b', 'y é'),       # il est -> y é
        (r'\bil y a\b', 'y a'),       # il y a -> y a
        (r'\bil\b', 'y'),             # il -> y
        (r'\bils\b', 'y'),            # ils -> y
        (r'\belle\b', 'a'),           # elle -> a
        (r'\belles\b', 'a'),          # elles -> a
        (r'\btu es\b', 't\'é'),       # tu es -> t'é

        # EXPRESSIONS BEAUCERONNES TYPIQUES
        (r'\bc\'est\b', 'cé'),        # c'est -> cé
        (r'c\'était', 'c\'tait'),     # c'était -> c'tait
        (r'\bparce que\b', 'pasque'), # parce que -> pasque
        (r'\bpuis\b', 'pi'),          # puis -> pi
        (r'\bavec\b', 'avec'),        # avec -> avec (prononcé "avèque")
        (r'ça fait que', 'ça faite que'),

        # PRONONCIATION DES FINALES (R roulé beauceron)
        (r'er\b', 'aaairre'),         # parler -> parlaaairre
        (r're\b', 'rre'),             # faire -> fairre
        (r'eur\b', 'eurrrre'),        # meilleur -> meilleurrre (r très roulé)
        (r'oir\b', 'ouèrrre'),        # avoir -> avouèrrre

        # EXPRESSIONS RÉGIONALES DE LA BEAUCE
        (r'\btrès\b', 'en maudit'),   # très -> en maudit (beauceron)
        (r'\bbeaucoup\b', 'en tabarouette'), # beaucoup -> en tabarouette
        (r'\bmaintenant\b', 'astheure'),     # maintenant -> astheure
        (r'\bau bout\b', 'au boutte'),       # au bout -> au boutte
        (r'\bc\'est plate\b', 'cé ben platte'),
        (r'\bpas mal\b', 'pas pire'),        # pas mal -> pas pire
        (r'\bvraiment\b', 'en crisse'),      # vraiment -> en crisse
        (r'\bd\'accord\b', 'correct'),       # d'accord -> correct
        (r'\boui\b', 'ouin'),                # oui -> ouin
        (r'\bnon\b', 'non non'),             # non -> non non (emphase)

        # PARTICULARITÉS PHONÉTIQUES BEAUCERONNES
        (r'qu([aeiou])', r'k\1'),     # que -> ke, qui -> ki
        (r'qui\b', 'ki'),             # qui -> ki
        (r'que\b', 'ke'),             # que -> ke
        (r'quoi', 'koué'),            # quoi -> koué
        (r'tion\b', 'ssionnng'),      # action -> acssionnng (nasalisé)
        (r'sion\b', 'ssionnng'),      # mission -> misssionnng
    ]

    result = text
    for pattern, replacement in transformations:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def run_tts(text: str, filename: str, instructions: str) -> tuple[bool, str]:
    """Generate TTS audio and write to `filename`.

    Returns tuple of (success: bool, generated_text: str).
    """
    cfg = get_config() or {}
    provider = str(cfg["tts_provider"]).lower().strip()
    voice = _normalize_voice(cfg["tts_voice"])
    sample_rate = int(cfg["tts_sample_rate"])
    edge_voice = cfg["tts_edge_voice"]
    fallback_on_refusal = bool(cfg["tts_fallback_on_refusal"])

    try:
        if provider == "edge":
            asyncio.run(_run_edge_tts(text, edge_voice, filename))
            return (True, text)

        audio_bytes, response_text = asyncio.run(
            _run_voice_agent_tts(text, instructions, voice, sample_rate)
        )
        if not audio_bytes:
            return (False, "")

        # Write PCM16 WAV file
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)

        if fallback_on_refusal and edge_tts is not None and _detect_refusal(response_text):
            try:
                asyncio.run(_run_edge_tts(text, edge_voice, filename))
                return (True, text)
            except Exception:
                pass

        spoken_text = response_text or text
        return (True, spoken_text)
    except Exception as ex:
        logging.error(f"TTS generation failed: {ex}")
        return (False, "")


def run_voice_generation_tts(
    user_prompt: str,
    system_prompt: str,
    filename: str,
    delivery_instructions: str,
    voice_override: Optional[str] = None,
) -> tuple[bool, str]:
    """Generate a spoken answer with Grok Voice API and return transcript.

    Returns tuple (success, transcript_text).
    """
    cfg = get_config() or {}
    voice = _normalize_voice(voice_override or cfg.get("tts_voice"))
    sample_rate = int(cfg.get("tts_sample_rate") or 24000)

    try:
        audio_bytes, transcript_text = asyncio.run(
            _run_voice_agent_generation(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                delivery_instructions=delivery_instructions,
                voice=voice,
                sample_rate=sample_rate,
            )
        )
        if not audio_bytes:
            return (False, "")

        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)

        return (True, (transcript_text or "").strip())
    except Exception as ex:
        logging.error(f"Voice generation failed: {ex}")
        return (False, "")


def run_voice_verbatim_tts(
    text: str,
    filename: str,
    delivery_instructions: str,
    voice_override: Optional[str] = "Leo",
    sample_rate: int = 16000,
) -> bool:
    """Low-latency Voice API TTS for Discord: strict verbatim speech, audio only."""
    voice = _normalize_voice(voice_override or "Leo")
    try:
        audio_bytes = asyncio.run(
            _run_voice_agent_verbatim_tts(
                text=text,
                delivery_instructions=delivery_instructions,
                voice=voice,
                sample_rate=sample_rate,
            )
        )
        if not audio_bytes:
            return False

        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        return True
    except Exception as ex:
        logging.error(f"Voice verbatim TTS failed: {ex}")
        return False





