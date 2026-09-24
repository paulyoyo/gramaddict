"""Steps every source handler shares: the per-user blacklist and
already-interacted checks, and the interact() call. They used to be copied
into each handler in handle_sources."""
import logging
from functools import partial
from typing import Optional

from GramAddict.core.storage import FollowingStatus
from GramAddict.core.utils import get_value

logger = logging.getLogger(__name__)


class SourceHandler:
    def __init__(self, ctx):
        self.ctx = ctx

    def is_blacklisted(self, username) -> bool:
        if self.ctx.storage.is_user_in_blacklist(username):
            logger.info(f"@{username} is in blacklist. Skip.")
            return True
        return False

    def may_interact_again(self, username) -> Optional[bool]:
        """None if we never interacted with username; otherwise whether
        can-reinteract-after has passed (logged either way)."""
        storage = self.ctx.storage
        interacted, interacted_when = storage.check_user_was_interacted(username)
        if not interacted:
            return None
        can_reinteract = storage.can_be_reinteract(
            interacted_when, get_value(self.ctx.args.can_reinteract_after, None, 0)
        )
        logger.info(
            f"@{username}: already interacted on {interacted_when:%Y/%m/%d %H:%M:%S}. {'Interacting again now' if can_reinteract else 'Skip'}."
        )
        return can_reinteract

    def interact_with(self, username, target=None) -> bool:
        """Interact with the profile that is open on screen and record it.
        Returns False when the source should stop (a limit was reached)."""
        ctx = self.ctx
        storage = ctx.storage
        target = ctx.source if target is None else target
        can_follow = False
        if ctx.is_follow_limit_reached is not None:
            can_follow = not ctx.is_follow_limit_reached() and storage.get_following_status(
                username
            ) in [FollowingStatus.NONE, FollowingStatus.NOT_IN_LIST]

        greeting_sink = {}
        (
            interaction_succeed,
            followed,
            requested,
            scraped,
            pm_sent,
            number_of_liked,
            number_of_watched,
            number_of_comments,
        ) = ctx.interaction(
            ctx.device,
            username=username,
            can_follow=can_follow,
            target=target,
            current_job=ctx.current_job,
            greeting_sink=greeting_sink,
        )

        add_interacted_user = partial(
            storage.add_interacted_user,
            session_id=ctx.session_state.id,
            job_name=ctx.current_job,
            target=target,
        )
        add_interacted_user(
            username,
            followed=followed,
            is_requested=requested,
            scraped=scraped,
            liked=number_of_liked,
            watched=number_of_watched,
            commented=number_of_comments,
            pm_sent=pm_sent,
        )
        # DJ greeting flow: queue the greeted user for the reply/AI conversation step.
        if greeting_sink:
            storage.enqueue_pending_reply(username, **greeting_sink)
        return ctx.on_interaction(
            succeed=interaction_succeed,
            followed=followed,
            scraped=scraped,
        )
