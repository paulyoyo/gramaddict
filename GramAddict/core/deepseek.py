import logging
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

# Classification results.
YES = "YES"
NO = "NO"
UNSURE = "UNSURE"

DEFAULT_MODEL = "deepseek-chat"
API_URL = "https://api.deepseek.com/chat/completions"

_CLASSIFIER_SYSTEM = (
    "You are a strict intent classifier for Instagram DM replies. "
    "Messages are usually in Spanish (Peru). "
    "Given a yes/no question about a user's message, answer with exactly ONE word: "
    "YES, NO, or UNSURE. Answer UNSURE if the message is ambiguous, off-topic, a "
    "question back, or needs a human. Output only the single word."
)


def load_deepseek_config(username) -> Optional[dict]:
    try:
        with open(f"accounts/{username}/deepseek.yml", "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as e:
        logger.error(f"DeepSeek configuration file not found: {e}")
        return None


def classify_intent(config: dict, question: str, reply_text: str) -> str:
    """Ask DeepSeek a yes/no question about the user's reply.

    Returns YES, NO, or UNSURE. Any error / unparseable answer -> UNSURE so the
    caller falls back to a human (Slack handoff) rather than guessing."""
    api_key = config.get("deepseek-api-key")
    if not api_key:
        logger.error("No 'deepseek-api-key' in deepseek.yml.")
        return UNSURE
    model = config.get("model", DEFAULT_MODEL)
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
                    {"role": "system", "content": _CLASSIFIER_SYSTEM},
                    {
                        "role": "user",
                        "content": f'Question: {question}\nUser message: "{reply_text}"\nAnswer:',
                    },
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().upper()
    except Exception as e:
        logger.error(f"Error calling DeepSeek: {e}")
        return UNSURE
    if answer.startswith(YES):
        return YES
    if answer.startswith(NO):
        return NO
    return UNSURE
