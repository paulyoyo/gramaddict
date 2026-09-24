import logging

from colorama import Fore

from GramAddict.core.device_facade import Direction, Timeout
from GramAddict.core.navigation import (
    nav_to_blogger,
)
from GramAddict.core.resources import ClassName
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.utils import (
    inspect_current_view,
    random_sleep,
)
from GramAddict.core.views import (
    case_insensitive_re,
)

logger = logging.getLogger(__name__)


class FollowersHandler(SourceHandler):
    """Interact with a blogger's followers or following."""

    def run(self, scroll_end_detector):
        device = self.ctx.device
        session_state = self.ctx.session_state
        username = self.ctx.source
        current_job = self.ctx.current_job
        is_myself = username == session_state.my_username
        if not nav_to_blogger(device, username, current_job):
            return

        self._iterate(is_myself, scroll_end_detector)

    def _iterate(self, is_myself, scroll_end_detector):
        device = self.ctx.device
        storage = self.ctx.storage
        current_job = self.ctx.current_job
        target = self.ctx.source
        profile_filter = self.ctx.profile_filter
        device.find(
            resourceId=self.ctx.resource_id.FOLLOW_LIST_CONTAINER,
            className=ClassName.LINEAR_LAYOUT,
        ).wait(Timeout.LONG)

        def scrolled_to_top():
            row_search = device.find(
                resourceId=self.ctx.resource_id.ROW_SEARCH_EDIT_TEXT,
                className=ClassName.EDIT_TEXT,
            )
            return row_search.exists()

        # Resume from saved position - fast scroll to where we left off
        saved_position = storage.get_source_position(target, current_job)
        users_scrolled = 0
        if saved_position > 0:
            logger.info(
                f"Resuming from position {saved_position} (previously processed users).",
                extra={"color": f"{Fore.CYAN}"},
            )
            list_view = device.find(
                resourceId=self.ctx.resource_id.LIST, className=ClassName.LIST_VIEW
            )
            if list_view.exists():
                # Fast scroll (fling) to approximate position
                flings_needed = saved_position // 10  # ~10 users per screen
                for i in range(min(flings_needed, 50)):  # Cap at 50 flings
                    list_view.fling(Direction.DOWN)
                    users_scrolled += 10
                logger.info(
                    f"Fast-scrolled past ~{users_scrolled} users.",
                    extra={"color": f"{Fore.CYAN}"},
                )

        total_users_processed = users_scrolled

        while True:
            logger.info("Iterate over visible followers.")
            screen_iterated_followers = []
            screen_skipped_followers_count = 0
            scroll_end_detector.notify_new_page()
            user_list = device.find(
                resourceIdMatches=self.ctx.resource_id.USER_LIST_CONTAINER,
            )
            row_height, n_users = inspect_current_view(user_list)
            try:
                for item in user_list:
                    cur_row_height = item.get_height()
                    if cur_row_height < row_height:
                        continue
                    user_info_view = item.child(index=1)
                    user_name_view = user_info_view.child(index=0).child()
                    if not user_name_view.exists():
                        logger.info(
                            "Next item not found: probably reached end of the screen.",
                            extra={"color": f"{Fore.GREEN}"},
                        )
                        break

                    username = user_name_view.get_text()
                    screen_iterated_followers.append(username)
                    scroll_end_detector.notify_username_iterated(username)

                    can_interact = False
                    if self.is_blacklisted(username):
                        pass  # logged
                    elif (
                        profile_filter is not None
                        and profile_filter.is_handler_blacklisted(username)
                    ):
                        pass  # Skip due to handler blacklist (message logged in filter function)
                    else:
                        again = self.may_interact_again(username)
                        if again:
                            can_interact = True
                        elif again is False:
                            screen_skipped_followers_count += 1
                        else:
                            can_interact = True

                    # Count every user we've seen (whether skipped or interacted)
                    total_users_processed += 1

                    if can_interact:
                        logger.info(
                            f"@{username}: interact", extra={"color": f"{Fore.YELLOW}"}
                        )
                        element_opened = user_name_view.click_retry()

                        if element_opened:
                            if not self.interact_with(username):
                                return
                        if element_opened:
                            logger.info("Back to followers list")
                            device.back()

                    # Save position after processing each user (whether interacted or skipped)
                    storage.save_source_position(
                        target, current_job, total_users_processed
                    )

            except IndexError:
                logger.info(
                    "Cannot get next item: probably reached end of the screen.",
                    extra={"color": f"{Fore.GREEN}"},
                )

            if is_myself and scrolled_to_top():
                logger.info(
                    "Scrolled to top, finish.", extra={"color": f"{Fore.GREEN}"}
                )
                storage.reset_source_position(target, current_job)
                return
            elif len(screen_iterated_followers) > 0:
                load_more_button = device.find(
                    resourceId=self.ctx.resource_id.ROW_LOAD_MORE_BUTTON
                )
                load_more_button_exists = load_more_button.exists()

                if scroll_end_detector.is_the_end():
                    logger.info(
                        "Reached end of list, resetting position for next time."
                    )
                    storage.reset_source_position(target, current_job)
                    return

                need_swipe = screen_skipped_followers_count == len(
                    screen_iterated_followers
                )
                list_view = device.find(
                    resourceId=self.ctx.resource_id.LIST, className=ClassName.LIST_VIEW
                )
                if not list_view.exists():
                    logger.error(
                        "Cannot find the list of followers. Trying to press back again."
                    )
                    device.back()
                    list_view = device.find(
                        resourceId=self.ctx.resource_id.LIST,
                        className=ClassName.LIST_VIEW,
                    )

                if is_myself:
                    logger.info("Need to scroll now", extra={"color": f"{Fore.GREEN}"})
                    list_view.scroll(Direction.UP)
                else:
                    pressed_retry = False
                    if load_more_button_exists:
                        retry_button = load_more_button.child(
                            className=ClassName.IMAGE_VIEW,
                            descriptionMatches=case_insensitive_re("Retry"),
                        )
                        if retry_button.exists():
                            random_sleep()
                            """It exist but can disappear without pressing on it"""
                            if retry_button.exists():
                                logger.info('Press "Load" button and wait few seconds.')
                                retry_button.click_retry()
                                random_sleep(5, 10, modulable=False)
                                pressed_retry = True

                    if need_swipe and not pressed_retry:
                        scroll_end_detector.notify_skipped_all()
                        if scroll_end_detector.is_skipped_limit_reached():
                            return
                        if scroll_end_detector.is_fling_limit_reached():
                            logger.info(
                                "Limit of all followers skipped reached, let's fling.",
                                extra={"color": f"{Fore.GREEN}"},
                            )
                            list_view.fling(Direction.DOWN)
                        else:
                            logger.info(
                                "All followers skipped, let's scroll.",
                                extra={"color": f"{Fore.GREEN}"},
                            )
                            list_view.scroll(Direction.DOWN)
                    else:
                        logger.info(
                            "Need to scroll now", extra={"color": f"{Fore.GREEN}"}
                        )
                        list_view.scroll(Direction.DOWN)
            else:
                logger.info(
                    "No followers were iterated, finish.",
                    extra={"color": f"{Fore.GREEN}"},
                )
                storage.reset_source_position(target, current_job)
                return
