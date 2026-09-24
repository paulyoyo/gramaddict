import logging
import os
from os import path

from atomicwrites import atomic_write
from colorama import Fore

from GramAddict.core.navigation import (
    nav_to_blogger,
)
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.utils import (
    get_value,
)
from GramAddict.core.views import (
    FollowingView,
    ProfileView,
    TabBarView,
    UniversalActions,
)

logger = logging.getLogger(__name__)


def do_unfollow_from_list(device, username, on_following_list):
    if not on_following_list:
        logger.warning("hola ke ase")
        ProfileView(device).click_on_avatar()
        if ProfileView(device).navigateToFollowing() and UniversalActions(
            device
        ).search_text(username):
            return FollowingView(device).do_unfollow_from_list(username)
    else:
        if username is not None:
            UniversalActions(device).search_text(username)
        return FollowingView(device).do_unfollow_from_list(username)


class BloggerHandler(SourceHandler):
    """Interact with the blogger's own profile."""

    def run(self):
        device = self.ctx.device
        blogger = self.ctx.source
        if not nav_to_blogger(device, blogger, self.ctx.current_job):
            return
        can_interact = False
        if self.is_blacklisted(blogger):
            pass  # logged
        else:
            # None = never interacted; False = interacted too recently
            can_interact = self.may_interact_again(blogger) is not False

        if can_interact:
            logger.info(
                f"@{blogger}: interact",
                extra={"color": f"{Fore.YELLOW}"},
            )
            if not self.interact_with(blogger):
                return


class BloggerFromFileHandler(SourceHandler):
    """Interact with (or unfollow) the usernames listed in a file."""

    def run(self):
        device = self.ctx.device
        parameter_passed = self.ctx.source
        current_job = self.ctx.current_job
        storage = self.ctx.storage
        need_to_refresh = True
        on_following_list = False
        limit_reached = False

        filename: str = os.path.join(
            storage.account_path, parameter_passed.split(" ")[0]
        )
        try:
            amount_of_users = get_value(parameter_passed.split(" ")[1], None, 10)
        except IndexError:
            amount_of_users = 10
            logger.warning(
                f"You didn't passed how many users should be processed from the list! Default is {amount_of_users} users."
            )
        if path.isfile(filename):
            with open(filename, "r", encoding="utf-8") as f:
                usernames = [line.replace(" ", "") for line in f if line != "\n"]
            len_usernames = len(usernames)
            if len_usernames < amount_of_users:
                amount_of_users = len_usernames
            logger.info(
                f"In {filename} there are {len_usernames} entries, {amount_of_users} users will be processed."
            )
            not_found = []
            processed_users = 0
            crashed = False
            try:
                for line, username_raw in enumerate(usernames, start=1):
                    username = username_raw.strip()
                    can_interact = False
                    if current_job == "unfollow-from-file":
                        unfollowed = do_unfollow_from_list(
                            device, username, on_following_list
                        )
                        on_following_list = True
                        if unfollowed:
                            storage.add_interacted_user(
                                username, self.ctx.session_state.id, unfollowed=True
                            )
                            self.ctx.session_state.totalUnfollowed += 1
                            limit_reached = self.ctx.session_state.check_limit(
                                limit_type=self.ctx.session_state.Limit.UNFOLLOWS
                            )
                            processed_users += 1
                        else:
                            not_found.append(username_raw)
                        if limit_reached:
                            logger.info("Unfollows limit reached.")
                            break
                        if processed_users == amount_of_users:
                            logger.info(
                                f"{processed_users} users have been unfollowed, going to the next job."
                            )
                            break
                    else:
                        if self.is_blacklisted(username):
                            pass  # logged
                        else:
                            # None = never interacted; False = interacted too recently
                            can_interact = (
                                self.may_interact_again(username) is not False
                            )

                        if not can_interact:
                            continue
                        if need_to_refresh:
                            search_view = TabBarView(device).navigateToSearch()
                        profile_view = search_view.navigate_to_target(
                            username, current_job
                        )
                        need_to_refresh = False
                        if not profile_view:
                            not_found.append(username_raw)
                            continue

                        if not self.interact_with(username, target=username):
                            return
                        device.back()
                        processed_users += 1
                        if processed_users == amount_of_users:
                            logger.info(
                                f"{processed_users} users have been interracted, going to the next job."
                            )
                            return
            except BaseException:
                crashed = True
                raise
            finally:
                if not_found:
                    with open(
                        f"{os.path.splitext(filename)[0]}_not_found.txt",
                        mode="a+",
                        encoding="utf-8",
                    ) as f:
                        f.writelines(not_found)
                if self.ctx.args.delete_interacted_users and len_usernames != 0:
                    with atomic_write(filename, overwrite=True, encoding="utf-8") as f:
                        # after a crash, keep the user who was being handled
                        f.writelines(usernames[line - 1 if crashed else line :])
        else:
            logger.warning(
                f"File {filename} not found. You have to specify the right relative path from this point: {os.getcwd()}"
            )
            return

        logger.info(f"Interact with users in {filename} completed.")
        device.back()
