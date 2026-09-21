import logging
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

# Sentinel the model is told to return when it can't confidently reply.
# The caller treats this (and any None/empty) as "needs a human".
NO_REPLY = "[[NO_REPLY]]"

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_SYSTEM_PROMPT = (
    "You are replying to Instagram direct messages on behalf of the account owner. "
    "Keep replies short, friendly and natural. "
    f"If you are unsure how to answer, or the message needs a human (a price quote, "
    f"a complaint, anything sensitive), reply with exactly {NO_REPLY} and nothing else."
)

API_URL = "https://api.deepseek.com/chat/completions"


def load_deepseek_config(username) -> Optional[dict]:
    try:
        with open(f"accounts/{username}/deepseek.yml", "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as e:
        logger.error(f"DeepSeek configuration file not found: {e}")
        return None


def generate_reply(config: dict, incoming_text: str) -> Optional[str]:
    """Ask DeepSeek for a reply. Returns the reply text, the NO_REPLY sentinel,
    or None on error. Mirrors the outbound-HTTP pattern in plugins/telegram.py."""
    api_key = config.get("deepseek-api-key")
    if not api_key:
        logger.error("No 'deepseek-api-key' in deepseek.yml.")
        return None
    model = config.get("model", DEFAULT_MODEL)
    system_prompt = config.get("system-prompt", DEFAULT_SYSTEM_PROMPT)
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": incoming_text},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Error calling DeepSeek: {e}")
        return None
