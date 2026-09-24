import logging

from colorama import Fore

from GramAddict.core.navigation import (
    nav_to_feed,
    nav_to_hashtag_or_place,
)
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.utils import (
    get_value,
    random_choice,
)
from GramAddict.core.views import (
    LikeMode,
    OpenedPostView,
    Owner,
    PostsViewList,
    SwipeTo,
    TabBarView,
    UniversalActions,
)

logger = logging.getLogger(__name__)


class PostsHandler(SourceHandler):
    """Interact with post owners in a hashtag, place or your own feed."""

    def run(self):
        device = self.ctx.device
        session_state = self.ctx.session_state
        target = self.ctx.source
        current_job = self.ctx.current_job
        profile_filter = self.ctx.profile_filter
        interact_percentage = self.ctx.percentages.interact
        scraping_file = self.ctx.args.scrape_to_file
        skipped_posts_limit = get_value(
            self.ctx.args.skipped_posts_limit,
            "Skipped post limit: {}",
            5,
        )
        if current_job == "feed":
            if scraping_file:
                logger.warning(
                    "Scraping and interacting with own feed doesn't make any sense. Skip."
                )
                return
            nav_to_feed(device)
            count_feed_limit = get_value(
                self.ctx.args.feed,
                "Feed interact count: {}",
                10,
            )
            count = 0
            PostsViewList(device)._refresh_feed()
        elif not nav_to_hashtag_or_place(device, target, current_job):
            return

        post_description = ""
        likes_failed = 0
        nr_same_post = 0
        nr_same_posts_max = 3
        nr_consecutive_already_interacted = 0
        already_liked_count = 0
        already_liked_count_limit = 20
        post_view_list = PostsViewList(device)
        opened_post_view = OpenedPostView(device)
        while True:
            (
                is_same_post,
                post_description,
                username,
                is_ad,
                is_hashtag,
                has_tags,
            ) = post_view_list._check_if_last_post(post_description, current_job)
            has_likers, number_of_likers = post_view_list._find_likers_container()
            already_liked, _ = opened_post_view._is_post_liked()
            if not (is_ad or is_hashtag):
                if already_liked_count == already_liked_count_limit:
                    logger.info(
                        f"Limit of {already_liked_count_limit} already liked posts limit reached, finish."
                    )
                    break
                if is_same_post:
                    nr_same_post += 1
                    logger.info(
                        f"Warning: {nr_same_post}/{nr_same_posts_max} repeated posts."
                    )
                    if nr_same_post == nr_same_posts_max:
                        logger.info(
                            f"Scrolled through {nr_same_posts_max} posts with same description and author. Finish."
                        )
                        break
                else:
                    nr_same_post = 0
                if already_liked:
                    logger.info(
                        "Post already liked, SKIP.", extra={"color": f"{Fore.CYAN}"}
                    )
                    already_liked_count += 1
                elif random_choice(interact_percentage):
                    can_interact = False
                    if self.is_blacklisted(username):
                        pass  # logged
                    elif (
                        profile_filter is not None
                        and profile_filter.is_handler_blacklisted(username)
                    ):
                        pass  # Skip due to handler blacklist (message logged in filter function)
                    else:
                        likes_in_range = profile_filter.is_num_likers_in_range(
                            number_of_likers
                        )
                        if current_job != "feed":
                            again = self.may_interact_again(username)
                            if again:
                                can_interact = True
                                nr_consecutive_already_interacted = 0
                            elif again is False:
                                nr_consecutive_already_interacted += 1
                            else:
                                can_interact = True
                                nr_consecutive_already_interacted = 0
                        else:
                            can_interact = True

                    if nr_consecutive_already_interacted == skipped_posts_limit:
                        logger.info(
                            f"Reached the limit of already interacted {skipped_posts_limit}. Going to the next source/job!"
                        )
                        break
                    if can_interact and (likes_in_range or not has_likers):
                        logger.info(
                            f"@{username}: interact", extra={"color": f"{Fore.YELLOW}"}
                        )
                        if scraping_file is None:
                            opened_post_view.start_video()
                            if not session_state.check_limit(
                                limit_type=session_state.Limit.LIKES, output=True
                            ):
                                if has_tags:
                                    post_view_list._like_in_post_view(
                                        LikeMode.SINGLE_CLICK
                                    )
                                else:
                                    post_view_list._like_in_post_view(
                                        LikeMode.DOUBLE_CLICK
                                    )
                                UniversalActions.detect_block(device)
                                liked = post_view_list._check_if_liked()
                                if not liked:
                                    post_view_list._like_in_post_view(
                                        LikeMode.SINGLE_CLICK, already_watched=True
                                    )
                                    UniversalActions.detect_block(device)
                                    liked = post_view_list._check_if_liked()
                                if liked:
                                    session_state.totalLikes += 1
                                    if current_job == "feed":
                                        count += 1
                                        logger.info(
                                            f"Interacted feed bloggers: {count}/{count_feed_limit}"
                                        )
                                        likes_limit = self.ctx.session_state.check_limit(
                                            limit_type=self.ctx.session_state.Limit.LIKES
                                        )
                                        success_limit = self.ctx.session_state.check_limit(
                                            limit_type=self.ctx.session_state.Limit.SUCCESS
                                        )
                                        total_limit = self.ctx.session_state.check_limit(
                                            limit_type=self.ctx.session_state.Limit.TOTAL
                                        )
                                        if likes_limit or success_limit or total_limit:
                                            logger.info("Limit reached, finish.")
                                            break
                                        if count >= count_feed_limit:
                                            logger.info(
                                                f"Interacted {count} bloggers in feed, finish."
                                            )
                                            break
                                else:
                                    likes_failed += 1
                        if current_job != "feed":
                            opened, _, _ = post_view_list._post_owner(
                                current_job, Owner.OPEN, username
                            )
                            if opened:
                                if not self.interact_with(username):
                                    break
                                device.back()
                else:
                    logger.info(
                        f"Skipped because your interact % is {interact_percentage}/100 and {username}'s post was unlucky!"
                    )
            if likes_failed == 10:
                logger.warning("You failed to do 10 likes! Soft-ban?!")
                return
            post_view_list.swipe_to_fit_posts(SwipeTo.HALF_PHOTO)
            post_view_list.swipe_to_fit_posts(SwipeTo.NEXT_POST)
        TabBarView(device).navigateToProfile()
