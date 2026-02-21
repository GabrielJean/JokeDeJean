import logging
import random
from collections import defaultdict, deque
from xai_sdk import Client
try:
    from xai_sdk.chat import user, system, assistant
except Exception:  # pragma: no cover - assistant helper may not exist
    from xai_sdk.chat import user, system  # type: ignore
    assistant = None  # type: ignore

"""GPT utility wrapper (xAI SDK).

Provides run_gpt() with robust handling of xAI SDK response shapes.
Imports get_config with a relative-first strategy so it functions under
`python -m discordbot.main` as well as direct script execution.
"""
try:
    from .bot_instance import get_config  # type: ignore
except Exception:  # pragma: no cover
    try:
        from bot_instance import get_config  # type: ignore
    except Exception:
        def get_config():  # type: ignore
            return {}

_client = None

def _get_client():
    global _client
    if _client is None:
        cfg = get_config()
        _client = Client(
            api_key=cfg["xai_api_key"],
            timeout=3600,
        )
    return _client


# --- Diversity & anti-repetition engine ---

_recent_outputs = defaultdict(lambda: deque(maxlen=8))

def _build_diversity_block(cfg, category=None):
    """Build a dynamic diversity instruction with generative angle/format seeds + anti-repeat."""
    parts = []
    base = cfg.get("gpt_diversity_instruction") or ""
    angles = cfg.get("diversity_angles") or []
    formats = cfg.get("diversity_formats") or []

    if base:
        parts.append(base)

    # Pick 2-3 random examples as *inspiration seeds*, not as direct instructions
    if angles or formats:
        seed_examples = []
        if angles:
            seed_examples += random.sample(angles, min(2, len(angles)))
        if formats:
            seed_examples += random.sample(formats, min(1, len(formats)))
        random.shuffle(seed_examples)
        seeds_text = "\n".join(f"  - {s}" for s in seed_examples)
        parts.append(
            "CRÉATIVITÉ OBLIGATOIRE: invente un angle comique et une structure "
            "COMPLÈTEMENT UNIQUES pour cette réponse. Ne réutilise JAMAIS un angle déjà fait. "
            f"Voici des exemples d'inspiration (NE LES COPIE PAS, invente le tien):\n{seeds_text}"
        )

    if category and _recent_outputs[category]:
        recent = list(_recent_outputs[category])[-5:]
        avoid_lines = "\n".join(f"- «{r[:150]}»" for r in recent)
        parts.append(
            f"INTERDICTION DE RÉPÉTER ou reformuler ces réponses récentes:\n{avoid_lines}"
        )

    return "\n\n".join(parts) if parts else ""


def _extract_response_text(response) -> str:
    # Try common response shapes from xAI SDK
    for attr in ("output_text", "text", "content"):
        val = getattr(response, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Try response.output list (Responses API style)
    output = getattr(response, "output", None)
    if isinstance(output, list):
        parts = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for c in content:
                    text = getattr(c, "text", None)
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
        if parts:
            return "\n".join(parts).strip()
    return ""


def _cfg_float(cfg: dict, key: str, default: float) -> float:
    try:
        val = cfg.get(key, default)
        if val is None:
            return float(default)
        return float(val)
    except Exception:
        return float(default)

def _sample_chat(chat, max_tokens: int, *, temperature: float, top_p: float,
                 frequency_penalty: float, presence_penalty: float):
    """Call chat.sample with best-effort support for optional parameters."""
    candidates = [
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "frequencyPenalty": frequency_penalty,
            "presencePenalty": presence_penalty,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "frequencyPenalty": frequency_penalty,
            "presencePenalty": presence_penalty,
        },
        {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "frequencyPenalty": frequency_penalty,
            "presencePenalty": presence_penalty,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        },
        {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        },
        {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
        {"max_tokens": max_tokens},
        {"max_output_tokens": max_tokens},
        {"maxOutputTokens": max_tokens},
        {},
    ]
    last_type_error = None
    for params in candidates:
        try:
            return chat.sample(**params)
        except TypeError as ex:
            last_type_error = ex
            continue
    if last_type_error:
        raise last_type_error
    return chat.sample()

def run_gpt(query, system_prompt=None, max_tokens=400, *, category=None):
    cfg = get_config()
    deployment = cfg.get("gpt_model") or "grok-4"
    prompts = cfg.get("prompts") or {}
    default_system = prompts.get("bot_system_prompt") or ""
    diversity_instruction = _build_diversity_block(cfg, category)
    temperature = _cfg_float(cfg, "gpt_temperature", 0.7)
    top_p = _cfg_float(cfg, "gpt_top_p", 1.0)
    frequency_penalty = _cfg_float(cfg, "gpt_frequency_penalty", 0.0)
    presence_penalty = _cfg_float(cfg, "gpt_presence_penalty", 0.0)
    try:
        client = _get_client()
        chat = client.chat.create(model=deployment, store_messages=False)

        # Allow both simple text and full messages list for multi-turn/multimodal
        if isinstance(query, list):
            messages = list(query)
            has_system = any(isinstance(m, dict) and m.get("role") in {"system", "developer"} for m in messages)
            if not has_system:
                sys_text = system_prompt or default_system
                if diversity_instruction:
                    sys_text = f"{sys_text}\n\n{diversity_instruction}"
                chat.append(system(sys_text))
            elif diversity_instruction:
                chat.append(system(diversity_instruction))
            for m in messages:
                role = m.get("role") if isinstance(m, dict) else None
                content = m.get("content") if isinstance(m, dict) else None
                if role in {"system", "developer"} and content:
                    if diversity_instruction and diversity_instruction not in content:
                        content = f"{content}\n\n{diversity_instruction}"
                    chat.append(system(content))
                elif role == "assistant" and content:
                    if assistant:
                        chat.append(assistant(content))
                    else:
                        chat.append({"role": "assistant", "content": content})
                elif content:
                    chat.append(user(content))
        else:
            sys_text = system_prompt or default_system
            if diversity_instruction:
                sys_text = f"{sys_text}\n\n{diversity_instruction}"
            chat.append(system(sys_text))
            chat.append(user(query))

        response = _sample_chat(
            chat,
            max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )
        text = _extract_response_text(response)
        if text:
            if category:
                _recent_outputs[category].append(text[:200])
            return text
        logging.error("Empty content from xAI response: %s", str(response)[:800])
        return "(aucune réponse)"
    except Exception as ex:
        logging.error(f"SDK request failed: {ex}")
        return "Erreur : impossible de contacter xAI."
