import logging
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
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        {
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        },
        {"max_tokens": max_tokens},
        {"max_output_tokens": max_tokens},
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

def run_gpt(query, system_prompt=None, max_tokens=400):
    cfg = get_config()
    deployment = cfg["gpt_model"]
    prompts = cfg["prompts"]
    default_system = prompts["bot_system_prompt"]
    diversity_instruction = cfg["gpt_diversity_instruction"]
    temperature = float(cfg["gpt_temperature"])
    top_p = float(cfg["gpt_top_p"])
    frequency_penalty = float(cfg["gpt_frequency_penalty"])
    presence_penalty = float(cfg["gpt_presence_penalty"])
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
            return text
        logging.error("Empty content from xAI response: %s", str(response)[:800])
        return "(aucune réponse)"
    except Exception as ex:
        logging.error(f"SDK request failed: {ex}")
        return "Erreur : impossible de contacter xAI."
