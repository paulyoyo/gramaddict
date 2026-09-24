import logging
import os
from dataclasses import replace
from os import path
from random import seed, shuffle

from colorama import Fore, Style

from GramAddict.core.decorators import run_safely
from GramAddict.core.sources import CommentersHandler, PostLikersHandler
from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.scroll_end_detector import ScrollEndDetector
from GramAddict.core.source_context import build_source_context, follow_limit_checker
from GramAddict.core.utils import (
    get_value,
    open_instagram_with_url,
    validate_url,
)
from GramAddict.core.views import OpenedPostView, PostsViewList

logger = logging.getLogger(__name__)

seed()


class InteractPostLikersCommentersFromURLs(Plugin):
    """Interacts with likers and commenters of posts specified by URLs"""

    def __init__(self):
        super().__init__()
        self.description = (
            "Interact with users who liked or commented on posts from URLs"
        )
        self.arguments = [
            {
                "arg": "--post-likers-commenters-from-file",
                "nargs": "+",
                "help": "file(s) containing post URLs to interact with their likers and commenters",
                "metavar": ("posts1.txt", "posts2.txt"),
                "default": None,
                "operation": True,
            },
            {
                "arg": "--interact-likers",
                "help": "interact with users who liked the posts (default: true)",
                "action": "store_true",
                "default": None,
            },
            {
                "arg": "--no-interact-likers",
                "help": "do not interact with likers",
                "action": "store_false",
                "dest": "interact_likers",
            },
            {
                "arg": "--interact-commenters",
                "help": "interact with users who commented on the posts (default: true)",
                "action": "store_true",
                "default": None,
            },
            {
                "arg": "--no-interact-commenters",
                "help": "do not interact with commenters",
                "action": "store_false",
                "dest": "interact_commenters",
            },
            {
                "arg": "--likers-limit-per-post",
                "nargs": None,
                "help": "max likers to interact with per post (e.g., 10-20)",
                "metavar": "10-20",
                "default": "10-15",
            },
            {
                "arg": "--commenters-limit-per-post",
                "nargs": None,
                "help": "max commenters to interact with per post (e.g., 5-10)",
                "metavar": "5-10",
                "default": "5-10",
            },
        ]

    def run(self, device, configs, storage, sessions, profile_filter, plugin):
        class State:
            def __init__(self):
                pass

            is_job_completed = False

        self.args = configs.args
        self.device = device
        self.device_id = configs.args.device
        self.state = None
        self.sessions = sessions
        self.session_state = sessions[-1]
        self.current_mode = plugin
        self.storage = storage
        self.profile_filter = profile_filter

        if self.args.interact_likers is None:
            self.args.interact_likers = True
        if self.args.interact_commenters is None:
            self.args.interact_commenters = True

        if not self.args.interact_likers and not self.args.interact_commenters:
            logger.warning(
                "Both --no-interact-likers and --no-interact-commenters specified. Nothing to do!"
            )
            return

        file_list = [file for file in self.args.post_likers_commenters_from_file]
        shuffle(file_list)

        for filename in file_list:
            (
                active_limits_reached,
                _,
                actions_limit_reached,
            ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)
            limit_reached = active_limits_reached or actions_limit_reached

            if limit_reached:
                logger.info("Likes and follows limit reached.")
                self.session_state.check_limit(
                    limit_type=self.session_state.Limit.ALL, output=True
                )
                break

            self.state = State()
            logger.info(
                f"Processing file: {filename}", extra={"color": f"{Style.BRIGHT}"}
            )

            ctx = build_source_context(
                self, device, storage, profile_filter, plugin, filename
            )

            @run_safely(
                device=self.device,
                device_id=self.device_id,
                sessions=self.sessions,
                session_state=self.session_state,
                screen_record=self.args.screen_record,
                configs=configs,
            )
            def job():
                self.process_file(filename, ctx)
                self.state.is_job_completed = True

            while not self.state.is_job_completed and not limit_reached:
                job()
                (
                    active_limits_reached,
                    _,
                    actions_limit_reached,
                ) = self.session_state.check_limit(
                    limit_type=self.session_state.Limit.ALL
                )
                limit_reached = active_limits_reached or actions_limit_reached

    def process_file(self, current_file, ctx):
        filename = os.path.join(self.storage.account_path, current_file.split(" ")[0])
        if not path.isfile(filename):
            logger.warning(f"File {current_file} not found.")
            return

        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            logger.info(f"Found {len(lines)} URLs in file.")

        for url in lines:
            (
                active_limits_reached,
                _,
                actions_limit_reached,
            ) = self.session_state.check_limit(limit_type=self.session_state.Limit.ALL)
            if active_limits_reached or actions_limit_reached:
                logger.info("Limits reached, stopping.")
                return

            if not self._is_valid_instagram_post_url(url):
                logger.warning(f"Invalid URL skipped: {url}")
                continue

            logger.info(
                f"Processing post: {url}",
                extra={"color": f"{Style.BRIGHT}{Fore.CYAN}"},
            )

            self.process_single_post(url, ctx)

    def _is_valid_instagram_post_url(self, url):
        if not validate_url(url):
            return False
        return "instagram.com/p/" in url or "instagram.com/reel/" in url

    def process_single_post(self, url, ctx):
        if not open_instagram_with_url(url):
            logger.warning(f"Could not open post: {url}")
            return

        # This post is the source: follows are counted per URL, not per file.
        post_ctx = replace(
            ctx,
            source=url,
            current_job="post-likers-commenters-from-file",
            is_follow_limit_reached=follow_limit_checker(
                self.args, self.session_state, url
            ),
        )

        skipped_list_limit = get_value(self.args.skipped_list_limit, None, 15)
        skipped_fling_limit = get_value(self.args.fling_when_skipped, None, 0)

        if self.args.interact_likers:
            self._interact_with_likers(
                post_ctx, skipped_list_limit, skipped_fling_limit
            )

        if self.args.interact_commenters:
            if not open_instagram_with_url(url):
                logger.warning(f"Could not reopen post for commenters: {url}")
            else:
                self._interact_with_commenters(
                    post_ctx, skipped_list_limit, skipped_fling_limit
                )

        logger.info("Going back from post...")
        self.device.back()

    def _interact_with_likers(self, ctx, skipped_list_limit, skipped_fling_limit):
        has_likers, number_of_likers = PostsViewList(self.device)._find_likers_container()

        if not has_likers:
            logger.info("No likers found for this post.")
            return

        if number_of_likers <= 1:
            logger.info(f"Only {number_of_likers} liker(s), skipping likers interaction.")
            return

        if not self.profile_filter.is_num_likers_in_range(number_of_likers):
            logger.info(f"Likers count ({number_of_likers}) not in filter range, skipping.")
            return

        logger.info(
            f"Found {number_of_likers} likers. Opening likers list...",
            extra={"color": f"{Fore.GREEN}"},
        )

        likers_limit = get_value(self.args.likers_limit_per_post, None, 15)
        likers_end_detector = ScrollEndDetector(
            repeats_to_end=2,
            skipped_list_limit=skipped_list_limit,
            skipped_fling_limit=skipped_fling_limit,
        )

        PostLikersHandler(ctx).run(likers_end_detector, likers_limit)

    def _interact_with_commenters(self, ctx, skipped_list_limit, skipped_fling_limit):
        commenters_limit = get_value(self.args.commenters_limit_per_post, None, 10)
        commenters_end_detector = ScrollEndDetector(
            repeats_to_end=2,
            skipped_list_limit=skipped_list_limit,
            skipped_fling_limit=skipped_fling_limit,
        )

        logger.info("Looking for commenters...", extra={"color": f"{Fore.GREEN}"})

        CommentersHandler(ctx).run(commenters_end_detector, commenters_limit)
