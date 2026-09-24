"""Everything a source handler needs for one source, built once per source.

Replaces the interact_with_user / follow-limit setup that every interact_* plugin
used to copy before calling a source handler.
"""
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from GramAddict.core.interaction import (
    interact_with_user,
    is_follow_limit_reached_for_source,
)
from GramAddict.core.resources import ResourceID as resources
from GramAddict.core.storage import InteractionStore
from GramAddict.core.utils import get_value, init_on_things


@dataclass(frozen=True)
class Percentages:
    stories: int
    likes: int
    follow: int
    comment: int
    pm: int
    interact: int


@dataclass
class SourceContext:
    device: Any
    args: Any
    session_state: Any
    resource_id: Any
    storage: InteractionStore
    profile_filter: Any
    current_job: str
    source: str
    on_interaction: Callable
    interaction: Callable
    is_follow_limit_reached: Callable[[], bool]
    percentages: Percentages


def follow_limit_checker(args, session_state, source: str) -> Callable[[], bool]:
    """True once the follow limit for `source` is reached (never, if no follow-limit)."""
    follow_limit = (
        get_value(args.follow_limit, None, 15)
        if args.follow_limit is not None
        else None
    )
    return partial(
        is_follow_limit_reached_for_source,
        session_state=session_state,
        follow_limit=follow_limit,
        source=source,
    )


def build_source_context(
    plugin, device, storage, profile_filter, current_job: str, source: str
) -> SourceContext:
    """`plugin` supplies args, sessions, session_state and current_mode."""
    args = plugin.args
    session_state = plugin.session_state
    (
        on_interaction,
        stories,
        likes,
        follow,
        comment,
        pm,
        interact,
    ) = init_on_things(source, args, plugin.sessions, session_state)
    percentages = Percentages(stories, likes, follow, comment, pm, interact)

    interaction = partial(
        interact_with_user,
        my_username=session_state.my_username,
        likes_count=args.likes_count,
        likes_percentage=percentages.likes,
        stories_percentage=percentages.stories,
        follow_percentage=percentages.follow,
        comment_percentage=percentages.comment,
        pm_percentage=percentages.pm,
        profile_filter=profile_filter,
        args=args,
        session_state=session_state,
        scraping_file=args.scrape_to_file,
        current_mode=plugin.current_mode,
    )
    return SourceContext(
        device=device,
        args=args,
        session_state=session_state,
        resource_id=resources(args.app_id),
        storage=storage,
        profile_filter=profile_filter,
        current_job=current_job,
        source=source,
        on_interaction=on_interaction,
        interaction=interaction,
        is_follow_limit_reached=follow_limit_checker(args, session_state, source),
        percentages=percentages,
    )
