import requests
from bot_instance import get_config

def run_gpt(query, system_prompt):
    config = get_config()
    try:
        resp = requests.post(
            config["azure_gpt_url"],
            headers={
                "api-key": config["api_key"],
                "Content-Type": "application/json"
            },
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                "max_tokens": 400
            },
            timeout=20
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            return "Erreur : la réponse d'Azure OpenAI a échoué."
    except Exception:
        return "Erreur : impossible de contacter Azure OpenAI."