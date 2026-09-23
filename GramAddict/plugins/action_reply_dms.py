import logging
import os
from datetime import datetime
from random import choice, randint, shuffle
from time import sleep

from colorama import Fore

from GramAddict.core.deepseek import (
    NO,
    UNSURE,
    YES,
    classify_intent,
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

# Questions posed to the DeepSeek classifier at each conversation stage.
Q_INTERESTED = "Does this reply show the person is interested in listening to the mix?"
Q_SOUNDCLOUD = "Does this reply say they use SoundCloud (or want the SoundCloud link)?"

# Peruvian Spanish defaults (override in deepseek.yml).
DEFAULT_YT_MSG = "¡Genial! Aquí está: {link} 🔥 ¿También usas SoundCloud?"
DEFAULT_SC_MSG = "Aquí está la versión de SoundCloud: {link} 🎧"


class ActionReplyDMs(Plugin):
    """Step 2+ of the DJ DM flow: read replies from users we greeted and drive a
    short, templated conversation (YouTube link -> ask SoundCloud -> SoundCloud
    link). DeepSeek only classifies intent; the code owns all text and links.
    Runs at most once per day."""

    def __init__(self):
        super().__init__()
        self.description = (
            "Read replies from users you greeted and continue the conversation "
            "(send YouTube link, ask about SoundCloud, send SoundCloud link). "
            "Runs once every ~24h. Configure 'deepseek.yml' (and optionally 'slack.yml')."
        )
        self.arguments = [
            {
                "arg": "--reply-dms",
                "nargs": None,
                "help": "check greeted users for replies and continue the DJ conversation",
                "metavar": "true",
                "default": None,
                "operation": True,
            },
            {
                "arg": "--reply-dms-min-hours",
                "nargs": None,
                "help": "minimum hours to wait after the last message before checking for a reply",
                "metavar": "3",
                "default": "3",
            },
            {
                "arg": "--reply-dms-limit",
                "nargs": None,
                "help": "max number of users to process per session (number or range)",
                "metavar": "10",
                "default": "10",
            },
            {
                "arg": "--reply-dms-delay",
                "nargs": None,
                "help": "seconds to pause before sending each reply, so it doesn't look instant (number or range). ~10%% of replies get an extra long pause.",
                "metavar": "15-90",
                "default": "15-90",
            },
            {
                "arg": "--dj-greeting-mode",
                "help": "step 1: send templated greetings (from deepseek.yml) instead of pm_list, and queue users for the AI reply conversation",
                "action": "store_true",
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
        self.slack_webhook = slack_config.get("slack-webhook-url") if slack_config else None
        self.cfg = deepseek_config

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
            logger.info("No greeted users due for a reply check.")
            self._mark_completed(storage)
            return

        logger.info(
            f"Checking {len(pending)} user(s) for replies.",
            extra={"color": f"{Fore.BLUE}"},
        )
        for entry in pending:
            target = entry.get("username")
            try:
                self._process_user(device, storage, entry, plugin)
            except Exception as e:
                logger.error(f"Error while handling @{target}: {e}")

        self._mark_completed(storage)

    def _process_user(self, device, storage, entry, plugin):
        target = entry.get("username")
        stage = entry.get("stage", "greeted")

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
            logger.info(f"@{target} hasn't replied yet. Keeping in queue.")
            device.back()
            return

        logger.info(f"@{target} (stage={stage}) replied: {reply_text!r}")

        if stage == "greeted":
            self._handle_greeted(device, storage, target, reply_text)
        elif stage == "sent_youtube":
            self._handle_sent_youtube(device, storage, target, reply_text)
        else:
            logger.warning(f"Unknown stage {stage!r} for @{target}; dropping.")
            storage.remove_pending_reply(target)
        device.back()

    def _handle_greeted(self, device, storage, target, reply_text):
        intent = classify_intent(self.cfg, Q_INTERESTED, reply_text)
        if intent == YES:
            msg = self._fill(self.cfg.get("youtube-messages"), DEFAULT_YT_MSG, self.cfg.get("youtube-link"))
            self._human_reply_pause(target)
            if msg and self._send_reply(device, msg):
                logger.info(f"Sent YouTube link to @{target}.", extra={"color": f"{Fore.GREEN}"})
                storage.update_pending_reply(target, stage="sent_youtube", sent_at=self._now())
            else:
                logger.warning(f"Could not send YouTube message to @{target}. Keeping in queue.")
        elif intent == NO:
            logger.info(f"@{target} not interested. Dropping.")
            storage.remove_pending_reply(target)
        else:
            self._handoff(target, reply_text, storage)

    def _handle_sent_youtube(self, device, storage, target, reply_text):
        intent = classify_intent(self.cfg, Q_SOUNDCLOUD, reply_text)
        if intent == YES:
            msg = self._fill(self.cfg.get("soundcloud-messages"), DEFAULT_SC_MSG, self.cfg.get("soundcloud-link"))
            self._human_reply_pause(target)
            if msg and self._send_reply(device, msg):
                logger.info(f"Sent SoundCloud link to @{target}. Done.", extra={"color": f"{Fore.GREEN}"})
            else:
                logger.warning(f"Could not send SoundCloud message to @{target}.")
            storage.remove_pending_reply(target)
        elif intent == NO:
            logger.info(f"@{target} doesn't use SoundCloud. Done.")
            storage.remove_pending_reply(target)
        else:
            self._handoff(target, reply_text, storage)

    def _handoff(self, target, reply_text, storage):
        logger.info(
            f"DeepSeek unsure about @{target}'s reply. Alerting via Slack for manual handling.",
            extra={"color": f"{Fore.YELLOW}"},
        )
        if self.slack_webhook:
            slack_send_text(
                self.slack_webhook,
                f":warning: Manual reply needed for @{target}: {reply_text}",
            )
        else:
            logger.warning("No slack.yml webhook configured; can't alert for handoff.")
        storage.remove_pending_reply(target)

    def _fill(self, templates, default_template, link):
        if not link:
            logger.error("No link configured in deepseek.yml for this step. Skipping send.")
            return None
        template = choice(templates) if templates else default_template
        return template.replace("{link}", link)

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

    def _human_reply_pause(self, target):
        # Replying in <1s is the one evidence-backed bot tell (velocity detection).
        # Draw a randomized pause; ~10% of the time add a "stepped away" long tail.
        delay = get_value(self.args.reply_dms_delay, None, 45)
        if randint(1, 10) == 1:
            delay += randint(60, 180)
        logger.info(f"Waiting {delay}s before replying to @{target} (human-like).")
        sleep(delay)

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
    def _now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

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
