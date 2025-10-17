import base64
import logging
import re
from openai import AzureOpenAI
"""TTS utility helper supporting multiple TTS services.

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

_tts_client = None

def _get_tts_client():
    """Get or create the OpenAI TTS client."""
    global _tts_client
    if _tts_client is None:
        cfg = get_config() or {}
        _tts_client = AzureOpenAI(
            azure_endpoint="https://gabri-ma4hd9yd-eastus2.openai.azure.com/",
            api_key=cfg.get("api_key"),
            api_version="2025-03-01-preview"
        )
    return _tts_client


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
    voice = cfg.get("tts_voice") or "echo"

    try:
        client = _get_tts_client()

        # Generate TTS with instructions
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            instructions=instructions
        )

        # Write to file
        response.stream_to_file(filename)

        return (True, text)
    except Exception as ex:
        logging.error(f"TTS generation failed: {ex}")
        return (False, "")





