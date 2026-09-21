import logging
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)


def load_slack_config(username) -> Optional[dict]:
    try:
        with open(f"accounts/{username}/slack.yml", "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError as e:
        logger.error(f"Slack configuration file not found: {e}")
        return None


def slack_send_text(webhook_url: str, text: str) -> bool:
    """Post a message to a Slack Incoming Webhook. Returns True on success."""
    if not webhook_url:
        logger.error("No Slack webhook url provided.")
        return False
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=15)
        return resp.ok
    except Exception as e:
        logger.error(f"Error sending Slack message: {e}")
        return False
