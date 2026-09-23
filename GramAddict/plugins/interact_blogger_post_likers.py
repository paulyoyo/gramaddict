import logging
from random import seed

from colorama import Style

from GramAddict.core.decorators import run_safely
from GramAddict.core.handle_sources import handle_likers
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.scroll_end_detector import ScrollEndDetector
from GramAddict.core.source_context import build_source_context
from GramAddict.core.utils import get_value, sample_sources

logger = logging.getLogger(__name__)

# Script Initialization
seed()


class InteractBloggerPostLikers(Plugin):
    """Handles the functionality of interacting with a blogger post likers"""

    def __init__(self):
        super().__init__()
        self.description = (
            "Handles the functionality of interacting with a blogger post likers"
        )
        self.arguments = [
            {
                "arg": "--blogger-post-likers",
                "nargs": "+",
                "help": "interact with likers of post for a specified blogger",
                "metavar": ("blogger1", "blogger2"),
                "default": None,
                "operation": True,
            },
            {
                "arg": "--blogger-post-limits",
                "nargs": None,
                "help": "limit the posts you're looking for likers",
                "metavar": "2",
                "default": 0,
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

        # Handle sources - fall back to blogger-followers if blogger-post-likers not defined
        if self.args.blogger_post_likers is not None:
            sources = [s for s in self.args.blogger_post_likers if s.strip()]
        elif self.args.blogger_followers is not None:
            sources = [s for s in self.args.blogger_followers if s.strip()]
            logger.info(
                "blogger-post-likers not defined, using blogger-followers as fallback.",
                extra={"color": f"{Style.BRIGHT}"},
            )
        else:
            logger.warning("No sources found for blogger-post-likers and no blogger-followers fallback available.")
            return
        for source in sample_sources(sources, self.args.truncate_sources):
            (
                active_limits_reached,
                _,
                actions_limit_reached,
            ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)
            limit_reached = active_limits_reached or actions_limit_reached

            self.state = State()
            logger.info(f"Handle {source}", extra={"color": f"{Style.BRIGHT}"})

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
                self.handle_blogger(ctx)
                self.state.is_job_completed = True

            while not self.state.is_job_completed and not limit_reached:
                job()

            if limit_reached:
                logger.info("Likes and follows limit reached.")
                self.session_state.check_limit(
                    limit_type=self.session_state.Limit.ALL, output=True
                )
                break

    def handle_blogger(self, ctx):
        skipped_list_limit = get_value(self.args.skipped_list_limit, None, 15)
        skipped_fling_limit = get_value(self.args.fling_when_skipped, None, 0)

        posts_end_detector = ScrollEndDetector(
            repeats_to_end=2,
            skipped_list_limit=skipped_list_limit,
            skipped_fling_limit=skipped_fling_limit,
        )

        handle_likers(
            self,
            ctx.device,
            ctx.session_state,
            ctx.source,
            ctx.current_job,
            ctx.storage,
            ctx.profile_filter,
            posts_end_detector,
            ctx.on_interaction,
            ctx.interaction,
            ctx.is_follow_limit_reached,
        )
