from openai import AzureOpenAI
import logging
from bot_instance import get_config

_client = None

def _get_client():
    global _client
    if _client is None:
        cfg = get_config()
        _client = AzureOpenAI(
            api_version=cfg.get("azure_api_version", "2024-12-01-preview"),
            azure_endpoint=cfg.get("azure_endpoint"),
            api_key=cfg.get("api_key"),
        )
    return _client

def run_gpt(query, system_prompt=None, max_tokens=400):
    cfg = get_config()
    deployment = cfg.get("gpt_model", "azure-gpt-5-nano")
    default_system = cfg.get("bot_system_prompt")
    try:
        client = _get_client()
        # Allow both simple text and full messages list for multi-turn/multimodal
        if isinstance(query, list):
            messages = list(query)
            # Ensure there's a system prompt at the start
            has_system = any(isinstance(m, dict) and m.get("role") == "system" for m in messages)
            if not has_system:
                sys_text = system_prompt or default_system or "You are a helpful assistant."
                messages.insert(0, {"role": "system", "content": sys_text})
        else:
            # Always include a system prompt (explicit > config > default)
            sys_text = system_prompt or default_system or "You are a helpful assistant."
            messages = [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": query}
            ]
        resp = client.chat.completions.create(
            messages=messages,
            max_completion_tokens=max_tokens,
            response_format={"type": "text"},
            model=deployment
        )
        try:
            choice = resp.choices[0]
            msg = choice.message
            # If the SDK returns a direct string
            if isinstance(getattr(msg, "content", None), str) and msg.content:
                return msg.content.strip()
            # If the SDK returns content parts (multimodal style)
            parts = getattr(msg, "content", None)
            collected = []
            if isinstance(parts, list):
                for p in parts:
                    try:
                        if isinstance(p, dict):
                            if p.get("type") == "text" and p.get("text"):
                                collected.append(p["text"]) 
                        else:
                            # Pydantic object with attributes
                            if getattr(p, "type", None) == "text" and getattr(p, "text", None):
                                collected.append(p.text)
                    except Exception:
                        continue
                if collected:
                    return "".join(collected).strip()
            # Refusal handling
            refusal = getattr(msg, "refusal", None)
            if refusal:
                logging.warning(f"Azure content refusal: {refusal}")
                return refusal.strip()
            # Log finish_reason and usage when content empty
            logging.error(
                "Azure 200 but empty content. finish_reason=%s, usage=%s, first_choice=%s",
                getattr(choice, "finish_reason", None),
                getattr(resp, "usage", None),
                str(choice)[:800]
            )
            # Retry once with a very small budget and a strict instruction to force output
            try:
                retry_messages = messages + [{"role": "system", "content": "Reply with ONE short sentence only. No analysis."}]
                retry_resp = client.chat.completions.create(
                    messages=retry_messages,
                    max_completion_tokens=min(64, max_tokens),
                    response_format={"type": "text"},
                    model=deployment
                )
                retry_choice = retry_resp.choices[0]
                retry_msg = retry_choice.message
                if isinstance(getattr(retry_msg, "content", None), str) and retry_msg.content:
                    return retry_msg.content.strip()
                retry_parts = getattr(retry_msg, "content", None)
                retry_collected = []
                if isinstance(retry_parts, list):
                    for p in retry_parts:
                        if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
                            retry_collected.append(p["text"])
                        elif getattr(p, "type", None) == "text" and getattr(p, "text", None):
                            retry_collected.append(p.text)
                if retry_collected:
                    return "".join(retry_collected).strip()
            except Exception as rex:
                logging.error(f"Retry after empty content failed: {rex}")
            return "(aucune réponse)"
        except Exception as ex:
            logging.error(f"Azure SDK unexpected response shape: {ex}; obj={resp}")
            return "(aucune réponse)"
    except Exception as ex:
        logging.error(f"Azure SDK request failed: {ex}")
        return "Erreur : impossible de contacter Azure OpenAI."
