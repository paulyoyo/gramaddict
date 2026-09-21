import logging
import os
from datetime import datetime
from random import randint, shuffle

from colorama import Fore

from GramAddict.core.deepseek import (
    NO_REPLY,
    generate_reply,
    load_deepseek_config,
)
from GramAddict.core.device_facade import Mode, Timeout
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.resources import ClassName
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.slack import load_slack_config, slack_send_text
from GramAddict.core.utils import get_value
from GramAddict.core.views import ProfileView, TabBarView

logger = logging.getLogger(__name__)

# Once-per-day check, but with a randomized window so it drifts instead of
# firing at a fixed clock hour.
COOLDOWN_MIN_HOURS = 20
COOLDOWN_MAX_HOURS = 28
COOLDOWN_FILE = "dm_reply_last_run.txt"


class ActionReplyDMs(Plugin):
    """Second step of the two-step DM flow: check users we PM'd for replies and
    answer them with a DeepSeek-generated message. Runs at most once per day."""

    def __init__(self):
        super().__init__()
        self.description = (
            "Check earlier PM recipients for replies and answer them via the DeepSeek AI. "
            "Runs once every ~24h. Configure 'deepseek.yml' (and optionally 'slack.yml' for "
            "manual-handoff alerts) in your account folder."
        )
        self.arguments = [
            {
                "arg": "--reply-dms",
                "nargs": None,
                "help": "check users we PM'd for replies and answer them with DeepSeek AI",
                "metavar": "true",
                "default": None,
                "operation": True,
            },
            {
                "arg": "--reply-dms-min-hours",
                "nargs": None,
                "help": "minimum hours to wait after the first PM before checking for a reply",
                "metavar": "3",
                "default": "3",
            },
            {
                "arg": "--reply-dms-limit",
                "nargs": None,
                "help": "max number of users to reply to per session (number or range)",
                "metavar": "10",
                "default": "10",
            },
        ]

    def run(self, device, configs, storage, sessions, profile_filter, plugin):
        self.args = configs.args
        self.ResourceID = resources(self.args.app_id)
        username = self.args.username

        if not self._can_run(storage):
            return

        deepseek_config = load_deepseek_config(username)
        if not deepseek_config:
            logger.error("No deepseek.yml found. Skipping reply-dms.")
            return

        slack_config = load_slack_config(username)
        slack_webhook = slack_config.get("slack-webhook-url") if slack_config else None

        min_hours = get_value(self.args.reply_dms_min_hours, "Reply DMs min hours: {}", 3)
        limit = get_value(self.args.reply_dms_limit, "Reply DMs limit: {}", 10)

        pending = [
            entry
            for entry in storage.get_pending_replies()
            if self._hours_since(entry.get("sent_at")) >= min_hours
        ]
        shuffle(pending)
        pending = pending[:limit]

        if not pending:
            logger.info("No PM recipients due for a reply check.")
            self._mark_completed(storage)
            return

        logger.info(
            f"Checking {len(pending)} user(s) for replies to our DMs.",
            extra={"color": f"{Fore.BLUE}"},
        )
        for entry in pending:
            target = entry.get("username")
            try:
                self._process_user(
                    device, storage, target, deepseek_config, slack_webhook, plugin
                )
            except Exception as e:
                logger.error(f"Error while checking @{target} for a reply: {e}")

        self._mark_completed(storage)

    def _process_user(
        self, device, storage, target, deepseek_config, slack_webhook, plugin
    ):
        # Open ONLY this user's thread, via their profile — never the general
        # inbox — so unrelated inbound messages are never opened or marked read.
        search_view = TabBarView(device).navigateToSearch()
        if not search_view.navigate_to_target(target, plugin):
            logger.warning(f"Could not open @{target}'s profile. Skipping.")
            return
        ProfileView(device, is_own_profile=False)

        message_button = device.find(
            classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
            enabled=True,
            textMatches="Message",
        )
        if not message_button.exists(Timeout.SHORT):
            logger.warning(f"No Message button on @{target}'s profile. Skipping.")
            return
        message_button.click()

        reply_text = self._read_last_reply(device)
        if not reply_text:
            # No reply yet — leave in queue, retry on the next daily check.
            logger.info(f"@{target} hasn't replied yet. Keeping in queue.")
            device.back()
            return

        logger.info(f"@{target} replied: {reply_text!r}")
        ai_reply = generate_reply(deepseek_config, reply_text)

        if not ai_reply or ai_reply == NO_REPLY:
            # DeepSeek isn't confident — hand off to the human via Slack.
            logger.info(
                f"DeepSeek can't confidently reply to @{target}. Alerting via Slack.",
                extra={"color": f"{Fore.YELLOW}"},
            )
            if slack_webhook:
                slack_send_text(
                    slack_webhook,
                    f":warning: Manual reply needed for @{target}: {reply_text}",
                )
            else:
                logger.warning("No slack.yml webhook configured; can't alert for handoff.")
            storage.remove_pending_reply(target)
            device.back()
            return

        if self._send_reply(device, ai_reply):
            logger.info(f"Replied to @{target}.", extra={"color": f"{Fore.GREEN}"})
            storage.remove_pending_reply(target)
        else:
            logger.warning(f"Failed to send reply to @{target}. Keeping in queue.")
        device.back()

    def _read_last_reply(self, device):
        """Return the text of the user's latest reply bubble, or None.

        ponytail: reads the last DM bubble as the reply. Distinguishing incoming
        vs outgoing bubbles reliably needs an on-device `gramaddict dump` (direction
        lives in the parent container / horizontal bounds) — refine _read_last_reply
        once that's inspected. Until then, the min-hours + once-daily gate keeps
        misfires low.
        """
        bubbles = device.find(resourceId=self.ResourceID.DIRECT_TEXT_MESSAGE_TEXT_VIEW)
        if not bubbles.exists(Timeout.SHORT):
            return None
        last_text = None
        for bubble in bubbles:
            text = bubble.get_text(error=False)
            if text:
                last_text = text
        return last_text

    def _send_reply(self, device, text) -> bool:
        message_box = device.find(
            resourceId=self.ResourceID.ROW_THREAD_COMPOSER_EDITTEXT,
            className=ClassName.EDIT_TEXT,
            enabled="true",
        )
        if not message_box.exists(Timeout.SHORT):
            return False
        message_box.set_text(text, Mode.PASTE if self.args.dont_type else Mode.TYPE)
        send_button = device.find(
            resourceId=self.ResourceID.ROW_THREAD_COMPOSER_BUTTON_SEND,
        )
        if not send_button.exists(Timeout.SHORT):
            return False
        send_button.click()
        return True

    @staticmethod
    def _hours_since(timestamp_str) -> float:
        if not timestamp_str:
            return float("inf")
        try:
            sent = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
            return (datetime.now() - sent).total_seconds() / 3600
        except (ValueError, TypeError):
            return float("inf")

    def _cooldown_path(self, storage):
        return os.path.join(storage.account_path, COOLDOWN_FILE)

    def _can_run(self, storage) -> bool:
        cooldown_file = self._cooldown_path(storage)
        if not os.path.exists(cooldown_file):
            return True
        try:
            with open(cooldown_file, "r") as f:
                last_run = datetime.fromisoformat(f.read().strip())
            hours_since = (datetime.now() - last_run).total_seconds() / 3600
            # Randomized window so the daily check time drifts.
            required = randint(COOLDOWN_MIN_HOURS, COOLDOWN_MAX_HOURS)
            if hours_since >= required:
                return True
            logger.info(
                f"reply-dms already ran {hours_since:.1f}h ago (< {required}h). Skip.",
                extra={"color": f"{Fore.YELLOW}"},
            )
            return False
        except Exception as e:
            logger.error(f"Error reading reply-dms cooldown file: {e}. Allowing run.")
            return True

    def _mark_completed(self, storage):
        try:
            with open(self._cooldown_path(storage), "w") as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.error(f"Error writing reply-dms cooldown file: {e}")
