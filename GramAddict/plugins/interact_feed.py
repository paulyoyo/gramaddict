import logging
from dataclasses import replace
from random import seed

from colorama import Style

from GramAddict.core.decorators import run_safely
from GramAddict.core.sources import PostsHandler
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.source_context import build_source_context

logger = logging.getLogger(__name__)

# Script Initialization
seed()


class InteractOwnFeed(Plugin):
    """Handles the functionality of interacting with your own feed"""

    def __init__(self):
        super().__init__()
        self.description = "Handles the functionality of interacting with your own feed"
        self.arguments = [
            {
                "arg": "--feed",
                "nargs": None,
                "help": "interact with your own feed",
                "metavar": "5-10",
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

        (
            active_limits_reached,
            _,
            actions_limit_reached,
        ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)
        limit_reached = active_limits_reached or actions_limit_reached

        self.state = State()
        logger.info("Interact with your own feed", extra={"color": f"{Style.BRIGHT}"})

        ctx = build_source_context(
            self, device, storage, profile_filter, plugin, "Own Feed"
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
            self.handle_feed(ctx)
            self.state.is_job_completed = True

        while not self.state.is_job_completed and not limit_reached:
            job()

        if limit_reached:
            logger.info("Ending session.")
            self.session_state.check_limit(
                limit_type=self.session_state.Limit.ALL, output=True
            )
            return

    def handle_feed(self, ctx):
        # own feed has no per-source follow limit
        PostsHandler(replace(ctx, is_follow_limit_reached=None)).run()
