import logging
import os
import re
import xml.etree.ElementTree as ET
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
from GramAddict.core.device_facade import DeviceFacade, Direction, Mode, Timeout
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.resources import ClassName
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.slack import load_slack_config, slack_send_text
from GramAddict.core.utils import get_value, open_instagram
from GramAddict.core.views import ProfileView, TabBarView, UniversalActions

logger = logging.getLogger(__name__)

# Hours between reply checks (--reply-dms-cooldown-hours). A range keeps the
# check time drifting instead of firing at a fixed clock hour.
DEFAULT_COOLDOWN_HOURS = "20-28"
COOLDOWN_FILE = "dm_reply_last_run.txt"

# Drop a queued user after this many visits with no way to open their DM.
MAX_UNREACHABLE = 3

# Replies that clearly mean "yes" to both of our questions, so they never go to
# DeepSeek (which read a bare "👍" as unsure). Variation selectors and skin
# tones are ignored.
_YES_WORDS = {
    "si", "sí", "sii", "siii", "sip", "dale", "claro", "ok", "okay", "okey",
    "va", "vale", "obvio", "ya", "porfa", "please", "plis", "bro", "hermano",
    "pasa", "pasalo", "pásalo", "manda", "mandalo", "mándalo", "yes", "sure",
}
_YES_EMOJI = set("👍👌🙌🔥❤💯👏🤙😍🥰💪✅🎶🎧")


def is_obvious_yes(text) -> bool:
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    emoji = [c for c in (text or "") if not c.isalnum() and not c.isspace()
             and c not in "!¡?¿.,;:'\"-\ufe0f\u200d"
             and not "\U0001F3FB" <= c <= "\U0001F3FF"]  # skin tones
    if not words and not emoji:
        return False
    return all(w in _YES_WORDS for w in words) and all(e in _YES_EMOJI for e in emoji) and (
        any(w in _YES_WORDS - {"bro", "hermano", "porfa", "please", "plis"} for w in words)
        or bool(emoji)
    )


# Outgoing DM bubbles end ~2% from the right screen edge; incoming ones start
# after the sender's avatar and end >=15% away (IG v300 dump, 720px wide).
OUTGOING_RIGHT_GAP = 0.06


def text_after_our_last_message(bubbles, screen_width):
    """bubbles: [(text, right_edge_px)] top to bottom. Returns the incoming
    texts after our last outgoing bubble, joined, or None if there are none."""
    incoming = []
    for text, right in bubbles:
        if screen_width - right < screen_width * OUTGOING_RIGHT_GAP:
            incoming = []  # ours: anything before it was already answered
        else:
            incoming.append(text)
    return " / ".join(incoming) or None


def unread_inbox_rows(hierarchy_xml: str):
    """Parse a DM inbox screen dump. Returns [(display_name, story_username)]
    for unread threads; story_username is None unless the row shows a story
    ring ("Open story of <username>"), the only place the username appears."""
    rows = []
    for row in ET.fromstring(hierarchy_xml).iter("node"):
        if not row.get("resource-id", "").endswith(":id/row_inbox_container"):
            continue
        desc = row.get("content-desc", "")
        name, _, rest = desc.partition(", ")
        if not rest.startswith("unread"):
            continue
        story_user = None
        for node in row.iter("node"):
            node_desc = node.get("content-desc", "")
            if node_desc.startswith("Open story of "):
                story_user = node_desc[len("Open story of "):].strip()
                break
        rows.append((name.strip(), story_user))
    return rows


def replied_first(pending, unread_rows):
    """Split the queue into (entries that look like an unread inbox thread,
    the rest). A loose match only changes check order: each thread is still
    opened by username and read before anything is sent."""
    names = {name.casefold() for name, _ in unread_rows}
    users = {user.casefold() for _, user in unread_rows if user}
    first_words = {name.split()[0].casefold() for name, _ in unread_rows if name.split()}

    def looks_unread(entry):
        username = (entry.get("username") or "").casefold()
        full_name = (entry.get("full_name") or "").casefold()
        first_name = (entry.get("first_name") or "").casefold()
        return (
            username in users
            or username in names
            or (full_name and full_name in names)
            or (first_name and first_name in first_words)
        )

    hits = [e for e in pending if looks_unread(e)]
    return hits, [e for e in pending if not looks_unread(e)]


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
    Runs at most once per --reply-dms-cooldown-hours."""

    def __init__(self):
        super().__init__()
        self.description = (
            "Read replies from users you greeted and continue the conversation "
            "(send YouTube link, ask about SoundCloud, send SoundCloud link). "
            "Runs every --reply-dms-cooldown-hours. Configure 'deepseek.yml' (and optionally 'slack.yml')."
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
                "arg": "--reply-dms-cooldown-hours",
                "nargs": None,
                "help": "hours between reply checks (number or range); 0 checks at the start of every session",
                "metavar": "20-28",
                "default": DEFAULT_COOLDOWN_HOURS,
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

        queue = storage.get_pending_replies()
        # People with an unread thread have replied: check them first, and
        # without waiting min_hours. Everyone else in random order.
        replied, _ = replied_first(queue, self._scan_inbox(device)) if queue else ([], [])
        due = [
            entry
            for entry in queue
            if entry not in replied and self._hours_since(entry.get("sent_at")) >= min_hours
        ]
        shuffle(replied)
        shuffle(due)
        if replied:
            logger.info(
                f"{len(replied)} queued user(s) have unread messages in the inbox. Checking them first.",
                extra={"color": f"{Fore.BLUE}"},
            )
        pending = (replied + due)[:limit]

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
            except DeviceFacade.AppHasCrashed:
                # Without this every remaining user fails in a second and the
                # next job starts with Instagram closed.
                logger.warning("Instagram closed during reply-dms. Reopening it.")
                if not open_instagram(device):
                    logger.error("Could not reopen Instagram. Ending this reply round.")
                    break
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
            self._count_unreachable(storage, entry)
            return
        ProfileView(device, is_own_profile=False)

        message_button = device.find(
            classNameMatches=ClassName.BUTTON_OR_TEXTVIEW_REGEX,
            enabled=True,
            textMatches="Message",
        )
        if not message_button.exists(Timeout.SHORT):
            logger.warning(f"No Message button on @{target}'s profile. Skipping.")
            self._count_unreachable(storage, entry)
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

    def _scan_inbox(self, device, pages=8):
        """Read-only: open the DM list, collect its unread rows, go back.
        Listing threads doesn't mark them read, and no thread is opened here."""
        try:
            thread_list = device.find(resourceId=self.ResourceID.INBOX_THREAD_LIST)
            # Already in the inbox (no tab bar there): navigating "home" would
            # fall back to a coordinate tap that lands on a thread row.
            if not thread_list.exists(Timeout.TINY):
                TabBarView(device).navigateToHome()
                inbox_button = device.find(resourceId=self.ResourceID.ACTION_BAR_INBOX_BUTTON)
                if not inbox_button.exists(Timeout.MEDIUM):
                    logger.info("DM inbox button not found; checking the queue in random order.")
                    return []
                inbox_button.click()
            if not thread_list.exists(Timeout.LONG):
                logger.info("DM inbox didn't load; checking the queue in random order.")
                device.back()
                return []
            # Instagram keeps the list's scroll position between visits; unread
            # threads are near the top.
            thread_list.fling(Direction.UP)
            rows, last_dump = [], None
            for _ in range(pages):
                dump = device.deviceV2.dump_hierarchy()
                if dump == last_dump:
                    break  # end of the list
                rows += [row for row in unread_inbox_rows(dump) if row not in rows]
                last_dump = dump
                thread_list.scroll(Direction.DOWN)
            device.back()
            logger.info(f"DM inbox: {len(rows)} unread thread(s) found.")
            return rows
        except Exception as e:
            logger.warning(f"Could not read the DM inbox ({e}); checking the queue in random order.")
            return []

    def _count_unreachable(self, storage, entry):
        target = entry.get("username")
        misses = entry.get("unreachable", 0) + 1
        if misses >= MAX_UNREACHABLE:
            logger.info(
                f"@{target} unreachable {misses} times (private or no DM). Dropping from queue."
            )
            storage.remove_pending_reply(target)
        else:
            storage.update_pending_reply(target, unreachable=misses)

    def _classify(self, question, reply_text):
        if is_obvious_yes(reply_text):
            return YES
        return classify_intent(self.cfg, question, reply_text)

    def _handle_greeted(self, device, storage, target, reply_text):
        intent = self._classify(Q_INTERESTED, reply_text)
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
        intent = self._classify(Q_SOUNDCLOUD, reply_text)
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
        """Return what the user wrote after our last message, or None if the
        last message in the thread is ours (they haven't replied yet)."""
        bubbles = device.find(resourceId=self.ResourceID.DIRECT_TEXT_MESSAGE_TEXT_VIEW)
        if not bubbles.exists(Timeout.SHORT):
            return None
        width = device.get_info()["displayWidth"]
        visible = []
        for bubble in bubbles:
            text = bubble.get_text(error=False)
            if text:
                visible.append((text, bubble.get_bounds()["right"]))
        return text_after_our_last_message(visible, width)

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
        # Otherwise the caller's back() only closes the keyboard and we stay in
        # the thread, where there is no tab bar to navigate from.
        UniversalActions.close_keyboard(device)
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
            required = get_value(self.args.reply_dms_cooldown_hours, None, 24)
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
