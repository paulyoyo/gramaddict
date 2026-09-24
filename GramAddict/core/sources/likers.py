import logging

from colorama import Fore

from GramAddict.core.device_facade import Direction, Timeout
from GramAddict.core.navigation import (
    nav_to_hashtag_or_place,
    nav_to_post_likers,
)
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.utils import (
    inspect_current_view,
)
from GramAddict.core.views import (
    OpenedPostView,
    PostsViewList,
    SwipeTo,
)

logger = logging.getLogger(__name__)


class LikersHandler(SourceHandler):
    """Interact with the likers of a hashtag, place or blogger's posts."""

    def run(self, posts_end_detector):
        device = self.ctx.device
        session_state = self.ctx.session_state
        target = self.ctx.source
        current_job = self.ctx.current_job
        profile_filter = self.ctx.profile_filter
        if (
            current_job == "blogger-post-likers"
            and not nav_to_post_likers(device, target, session_state.my_username)
            or current_job != "blogger-post-likers"
            and not nav_to_hashtag_or_place(device, target, current_job)
        ):
            return False
        post_description = ""
        nr_same_post = 0
        nr_same_posts_max = 3
        while True:
            flag, post_description, _, _, _, _ = PostsViewList(
                device
            )._check_if_last_post(post_description, current_job)
            has_likers, number_of_likers = PostsViewList(
                device
            )._find_likers_container()
            if flag:
                nr_same_post += 1
                logger.info(
                    f"Warning: {nr_same_post}/{nr_same_posts_max} repeated posts."
                )
                if nr_same_post == nr_same_posts_max:
                    logger.info(
                        f"Scrolled through {nr_same_posts_max} posts with same description and author. Finish.",
                        extra={"color": f"{Fore.CYAN}"},
                    )
                    break
            else:
                nr_same_post = 0

            if (
                has_likers
                and profile_filter.is_num_likers_in_range(number_of_likers)
                and number_of_likers != 1
            ):
                PostsViewList(device).open_likers_container()
            else:
                PostsViewList(device).swipe_to_fit_posts(SwipeTo.NEXT_POST)
                continue

            posts_end_detector.notify_new_page()

            likes_list_view = OpenedPostView(device)._getListViewLikers()
            if likes_list_view is None:
                return
            prev_screen_iterated_likers = []

            while True:
                logger.info("Iterate over visible likers.")
                screen_iterated_likers = []
                opened = False
                user_container = OpenedPostView(device)._getUserContainer()
                if user_container is None:
                    logger.warning("Likers list didn't load :(")
                    return
                row_height, n_users = inspect_current_view(user_container)
                try:
                    for item in user_container:
                        cur_row_height = item.get_height()
                        if cur_row_height < row_height:
                            continue
                        element_opened = False
                        username_view = OpenedPostView(device)._getUserName(item)
                        if not username_view.exists(Timeout.MEDIUM):
                            logger.info(
                                "Next item not found: probably reached end of the screen.",
                                extra={"color": f"{Fore.GREEN}"},
                            )
                            break

                        username = username_view.get_text()
                        screen_iterated_likers.append(username)
                        posts_end_detector.notify_username_iterated(username)
                        can_interact = False
                        if self.is_blacklisted(username):
                            pass  # logged
                        else:
                            # None = never interacted; False = interacted too recently
                            can_interact = (
                                self.may_interact_again(username) is not False
                            )

                        if can_interact:
                            logger.info(
                                f"@{username}: interact",
                                extra={"color": f"{Fore.YELLOW}"},
                            )
                            element_opened = username_view.click_retry()

                            if element_opened and not self.interact_with(username):
                                return
                        if element_opened:
                            opened = True
                            logger.info("Back to likers list.")
                            device.back()

                except IndexError:
                    logger.info(
                        "Cannot get next item: probably reached end of the screen.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    break
                go_back = False
                if screen_iterated_likers == prev_screen_iterated_likers:
                    logger.info(
                        "Iterated exactly the same likers twice.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    go_back = True
                if go_back:
                    prev_screen_iterated_likers.clear()
                    prev_screen_iterated_likers += screen_iterated_likers
                    logger.info(
                        f"Back to {target}'s posts list.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    device.back()
                    logger.info("Going to the next post.")
                    PostsViewList(device).swipe_to_fit_posts(SwipeTo.NEXT_POST)
                    break
                if posts_end_detector.is_fling_limit_reached():
                    logger.info(
                        "Reached fling limit. Fling to see other likers.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    likes_list_view.fling(Direction.DOWN)
                else:
                    logger.info(
                        "Scroll to see other likers.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    likes_list_view.scroll(Direction.DOWN)

                prev_screen_iterated_likers.clear()
                prev_screen_iterated_likers += screen_iterated_likers
                if posts_end_detector.is_the_end():
                    device.back()
                    PostsViewList(device).swipe_to_fit_posts(SwipeTo.NEXT_POST)
                    break
                if not opened:
                    logger.info(
                        "All likers skipped.",
                        extra={"color": f"{Fore.GREEN}"},
                    )
                    posts_end_detector.notify_skipped_all()
                    if posts_end_detector.is_skipped_limit_reached():
                        posts_end_detector.reset_skipped_all()
                        return
