import logging

from colorama import Fore

from GramAddict.core.device_facade import Direction, Timeout
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.utils import (
    inspect_current_view,
    random_sleep,
)
from GramAddict.core.views import (
    OpenedPostView,
    PostsViewList,
)

logger = logging.getLogger(__name__)


class PostLikersHandler(SourceHandler):
    """Interact with the likers of a post opened from a URL."""

    def run(self, likers_end_detector, likers_limit):
        """Iterate over likers of a post from URL and interact with them."""
        device = self.ctx.device
        session_state = self.ctx.session_state
        PostsViewList(device).open_likers_container()

        likes_list_view = OpenedPostView(device)._getListViewLikers()
        if likes_list_view is None:
            logger.warning("Could not load likers list.")
            device.back()
            return

        likers_interacted = 0
        prev_screen_iterated_likers = []

        while likers_interacted < likers_limit:
            logger.info("Iterate over visible likers.")
            screen_iterated_likers = []
            opened = False

            likers_end_detector.notify_new_page()

            user_container = OpenedPostView(device)._getUserContainer()
            if user_container is None:
                logger.warning("Likers list didn't load :(")
                device.back()
                return

            row_height, n_users = inspect_current_view(user_container)

            try:
                for item in user_container:
                    if likers_interacted >= likers_limit:
                        break

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
                    likers_end_detector.notify_username_iterated(username)

                    can_interact = False
                    if self.is_blacklisted(username):
                        pass  # logged
                    elif username == session_state.my_username:
                        logger.info("It's you, skip.")
                    else:
                        # None = never interacted; False = interacted too recently
                        can_interact = self.may_interact_again(username) is not False

                    if can_interact:
                        logger.info(
                            f"@{username}: interact (liker)",
                            extra={"color": f"{Fore.YELLOW}"},
                        )
                        element_opened = username_view.click_retry()

                        if element_opened and not self.interact_with(username):
                            device.back()
                            return

                        if element_opened:
                            likers_interacted += 1

                    if element_opened:
                        opened = True
                        logger.info("Back to likers list.")
                        device.back()

            except IndexError:
                logger.info(
                    "Cannot get next item: probably reached end of the screen.",
                    extra={"color": f"{Fore.GREEN}"},
                )

            go_back = False
            if screen_iterated_likers == prev_screen_iterated_likers:
                logger.info(
                    "Iterated exactly the same likers twice.",
                    extra={"color": f"{Fore.GREEN}"},
                )
                go_back = True

            if go_back or likers_end_detector.is_the_end():
                logger.info("Finished with likers for this post.")
                device.back()
                return

            prev_screen_iterated_likers.clear()
            prev_screen_iterated_likers += screen_iterated_likers

            if not opened:
                logger.info("All likers skipped.", extra={"color": f"{Fore.GREEN}"})
                likers_end_detector.notify_skipped_all()
                if likers_end_detector.is_skipped_limit_reached():
                    device.back()
                    return

            if likers_end_detector.is_fling_limit_reached():
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

        logger.info(f"Reached likers limit ({likers_limit}). Done with likers.")
        device.back()


class CommentersHandler(SourceHandler):
    """Interact with the commenters of a post opened from a URL."""

    def run(self, comments_end_detector, commenters_limit):
        """Iterate over commenters of a post and interact with them."""
        device = self.ctx.device
        session_state = self.ctx.session_state
        opened_post_view = OpenedPostView(device)

        if not opened_post_view.open_comments_section():
            logger.warning("Could not open comments section.")
            return

        random_sleep(inf=2, sup=3, modulable=False)

        comments_container = opened_post_view.get_comments_container()
        if comments_container is None:
            logger.warning("Could not find comments container.")
            device.back()
            return

        commenters_interacted = 0
        prev_screen_commenters = []
        post_owner = None

        try:
            post_owner_view = device.find(
                resourceIdMatches=self.ctx.resource_id.ROW_FEED_PHOTO_PROFILE_NAME
            )
            if post_owner_view.exists():
                post_owner = post_owner_view.get_text().strip().split()[0]
        except Exception as e:
            # only used to skip the post owner among commenters
            logger.debug(f"Could not read the post owner: {type(e).__name__}: {e}")

        while commenters_interacted < commenters_limit:
            logger.info("Iterate over visible commenters.")
            screen_commenters = []
            opened = False

            comments_end_detector.notify_new_page()

            try:
                for comment_row in comments_container:
                    if commenters_interacted >= commenters_limit:
                        break

                    username, username_view = opened_post_view.get_commenter_username(
                        comment_row
                    )

                    if not username:
                        continue

                    if post_owner and username.lower() == post_owner.lower():
                        logger.debug(f"Skipping post owner: {username}")
                        continue

                    screen_commenters.append(username)
                    comments_end_detector.notify_username_iterated(username)

                    can_interact = False
                    if self.is_blacklisted(username):
                        pass  # logged
                    elif username == session_state.my_username:
                        logger.info("It's you, skip.")
                    else:
                        # None = never interacted; False = interacted too recently
                        can_interact = self.may_interact_again(username) is not False

                    if can_interact:
                        logger.info(
                            f"@{username}: interact (commenter)",
                            extra={"color": f"{Fore.YELLOW}"},
                        )

                        element_opened = False
                        if username_view is not None:
                            element_opened = username_view.click_retry()

                        if element_opened and not self.interact_with(username):
                            device.back()
                            return

                        if element_opened:
                            commenters_interacted += 1
                            opened = True
                            logger.info("Back to comments list.")
                            device.back()
                            random_sleep(inf=1, sup=2, modulable=False)

            except IndexError:
                logger.info(
                    "Cannot get next item: probably reached end of the comments.",
                    extra={"color": f"{Fore.GREEN}"},
                )

            go_back = False
            if (
                screen_commenters == prev_screen_commenters
                and len(screen_commenters) > 0
            ):
                logger.info(
                    "Iterated exactly the same commenters twice.",
                    extra={"color": f"{Fore.GREEN}"},
                )
                go_back = True

            if go_back or comments_end_detector.is_the_end():
                logger.info("Finished with commenters for this post.")
                device.back()
                return

            prev_screen_commenters.clear()
            prev_screen_commenters += screen_commenters

            if not opened and len(screen_commenters) > 0:
                logger.info("All commenters skipped.", extra={"color": f"{Fore.GREEN}"})
                comments_end_detector.notify_skipped_all()
                if comments_end_detector.is_skipped_limit_reached():
                    device.back()
                    return

            if len(screen_commenters) > 0:
                logger.info(
                    "Scroll to see more comments.", extra={"color": f"{Fore.GREEN}"}
                )
                comments_container.scroll(Direction.DOWN)
                random_sleep(inf=1, sup=2, modulable=False)
            else:
                logger.info("No commenters found on this screen.")
                break

        logger.info(
            f"Reached commenters limit ({commenters_limit}). Done with commenters."
        )
        device.back()
