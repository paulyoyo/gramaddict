import logging
import re
from random import uniform
from time import sleep
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

# Classification results.
YES = "YES"
NO = "NO"
UNSURE = "UNSURE"
# DeepSeek could not be reached (network, 429/5xx, bad key): not an answer.
ERROR = "ERROR"

ATTEMPTS = 3
BACKOFF_SECONDS = 2

DEFAULT_MODEL = "deepseek-chat"
API_URL = "https://api.deepseek.com/chat/completions"

_CLASSIFIER_SYSTEM = (
    "You are a strict intent classifier for Instagram DM replies. "
    "Messages are usually in Spanish (Peru). "
    "Given a yes/no question about a user's message, answer with exactly ONE word: "
    "YES, NO, or UNSURE. A short affirmative reply (e.g. 'sí', 'dale', 'claro', "
    "👍, 🔥, 🙌) to our question counts as YES. Answer UNSURE if the message is "
    "ambiguous, off-topic, a question back, or needs a human. Output only the single word."
)


class _Retryable(Exception):
    pass


def load_deepseek_config(username) -> Optional[dict]:
    try:
        with open(f"accounts/{username}/deepseek.yml", "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as e:
        logger.error(f"DeepSeek configuration file not found: {e}")
        return None


def classify_intent(config: dict, question: str, reply_text: str) -> str:
    """Ask DeepSeek a yes/no question about the user's reply.

    Returns YES, NO or UNSURE for a real answer (anything unrecognised is
    UNSURE, so a human decides), or ERROR when DeepSeek could not be reached
    after retries: the caller keeps the user queued and tries again later."""
    api_key = config.get("deepseek-api-key")
    if not api_key:
        logger.error("No 'deepseek-api-key' in deepseek.yml.")
        return ERROR
    model = config.get("model", DEFAULT_MODEL)
    for attempt in range(1, ATTEMPTS + 1):
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
            if resp.status_code == 429 or resp.status_code >= 500:
                raise _Retryable(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return parse_answer(resp.json()["choices"][0]["message"]["content"])
        except (_Retryable, requests.Timeout, requests.ConnectionError) as e:
            if attempt == ATTEMPTS:
                logger.error(f"DeepSeek unavailable after {ATTEMPTS} tries ({e}).")
                return ERROR
            delay = BACKOFF_SECONDS * 2 ** (attempt - 1) + uniform(0, 1)
            logger.warning(f"DeepSeek call failed ({e}); retrying in {delay:.0f}s.")
            sleep(delay)
        except Exception as e:
            # 4xx other than 429, or an unexpected response shape: retrying won't help.
            logger.error(f"Error calling DeepSeek: {type(e).__name__}: {e}")
            return ERROR
    return ERROR


def parse_answer(content: str) -> str:
    """First word of the model's answer; "NOT SURE", "NONE" etc. are UNSURE."""
    match = re.search(r"[A-Za-z]+", content or "")
    word = match[0].upper() if match else ""
    return word if word in (YES, NO) else UNSURE
