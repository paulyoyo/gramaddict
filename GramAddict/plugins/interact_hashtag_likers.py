import logging
from random import seed

import emoji
from colorama import Fore

from GramAddict.core.decorators import run_safely
from GramAddict.core.sources import LikersHandler
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.scroll_end_detector import ScrollEndDetector
from GramAddict.core.source_context import build_source_context
from GramAddict.core.utils import get_value, sample_sources

logger = logging.getLogger(__name__)

# Script Initialization
seed()


class InteractHashtagLikers(Plugin):
    """Handles the functionality of interacting with a hashtags likers"""

    def __init__(self):
        super().__init__()
        self.description = (
            "Handles the functionality of interacting with a hashtags likers"
        )
        self.arguments = [
            {
                "arg": "--hashtag-likers-top",
                "nargs": "+",
                "help": "list of hashtags in top results with whose likers you want to interact",
                "metavar": ("hashtag1", "hashtag2"),
                "default": None,
                "operation": True,
            },
            {
                "arg": "--hashtag-likers-recent",
                "nargs": "+",
                "help": "list of hashtags in recent results with whose likers you want to interact",
                "metavar": ("hashtag1", "hashtag2"),
                "default": None,
                "operation": True,
            },
        ]

    def run(self, device, configs, storage, sessions, profile_filter, plugin):
        class State:
            def __init__(self):
                pass

            is_job_completed = False

        self.device_id = configs.args.device
        self.sessions = sessions
        self.session_state = sessions[-1]
        self.args = configs.args
        self.current_mode = plugin

        # IMPORTANT: in each job we assume being on the top of the Profile tab already
        sources = [
            source
            for source in (
                self.args.hashtag_likers_top
                if self.current_mode == "hashtag-likers-top"
                else self.args.hashtag_likers_recent
            )
        ]
        # Start
        for source in sample_sources(sources, self.args.truncate_sources):
            (
                active_limits_reached,
                _,
                actions_limit_reached,
            ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)
            limit_reached = active_limits_reached or actions_limit_reached
            self.state = State()
            if source[0] != "#":
                source = "#" + source
            logger.info(
                f"Handle {emoji.emojize(source, use_aliases=True)}",
                extra={"color": f"{Fore.BLUE}"},
            )

            ctx = build_source_context(
                self, device, storage, profile_filter, plugin, source
            )

            @run_safely(
                device=device,
                device_id=self.device_id,
                sessions=self.sessions,
                session_state=self.session_state,
                screen_record=self.args.screen_record,
                configs=configs,
            )
            def job():
                self.handle_hashtag(ctx)
                self.state.is_job_completed = True

            while not self.state.is_job_completed and not limit_reached:
                job()

            if limit_reached:
                logger.info("Ending session.")
                self.session_state.check_limit(
                    limit_type=self.session_state.Limit.ALL, output=True
                )
                break

    def handle_hashtag(self, ctx):
        skipped_list_limit = get_value(self.args.skipped_list_limit, None, 15)
        skipped_fling_limit = get_value(self.args.fling_when_skipped, None, 0)

        posts_end_detector = ScrollEndDetector(
            repeats_to_end=2,
            skipped_list_limit=skipped_list_limit,
            skipped_fling_limit=skipped_fling_limit,
        )

        LikersHandler(ctx).run(posts_end_detector)
