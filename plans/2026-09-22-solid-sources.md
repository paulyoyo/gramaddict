# Batch 7 — SOLID restructuring of source handling and storage

Decision 7 in `plans/audit-2026-09-22.md`: rubric tensions are resolved toward SOLID.
No upstream sync (decision 4), so file moves and renames are fine.

## Problem

- `core/handle_sources.py` (1,250 lines) exposes 8 module functions that take the calling
  plugin as a fake `self` (only for `.args`, `.session_state`, `.ResourceID`) plus 9–12
  positional arguments. Call sites are easy to get wrong silently: `profile_filter` is
  positional in some handlers and keyword-optional in others.
- 9 plugins (`interact_blogger*`, `interact_hashtag_*`, `interact_place_*`, `interact_feed`,
  `interact_post_likers_commenters_from_urls`) each rebuild the same objects before calling a
  handler: the `interact_with_user` partial (11 bound args), the
  `is_follow_limit_reached_for_source` partial, and the `init_on_things` percentages.
- Core logic talks to the concrete JSON `Storage`, so the handlers and filters can't be
  unit-tested without files on disk and an `accounts/` folder.

## Constraints

- No behavior change. Every step is a pure refactor, and the run logs should read the same.
- Device flows have no automated tests. The real check is a phone run per step.
- Keep `@run_safely` and the job and limit loops in the plugins as they are (out of scope).
- Unfollow and remove-followers plugins don't use `handle_sources`, so they're out of scope.

## Design

1. **`SourceContext` dataclass** (`core/source_context.py`)
   Fields: `device, args, session_state, resource_id, storage, profile_filter, current_job,
   target, on_interaction, interaction, is_follow_limit_reached`.
   One factory, `build_source_context(plugin, device, storage, profile_filter, source,
   current_job, percentages)`, replaces the duplicated partial setup in the 9 plugins.
2. **Handler classes** (`core/sources/`)
   `SourceHandler` base holds the shared steps that are copy-pasted today: the `interact()`
   wrapper, the skip / blacklist / already-interacted checks, and `save_source_position`.
   One subclass per source, each with `run()`: `BloggerHandler`, `BloggerFromFileHandler`,
   `LikersHandler`, `PostsHandler`, `FollowersHandler`, `PostLikersHandler`,
   `CommentersHandler`. Handler-specific inputs (end detector, limits, `scraping_file`)
   become constructor arguments.
3. **Storage protocol** (`core/storage.py`)
   `class InteractionStore(Protocol)` with the 12 methods core code calls (interacted users,
   filter users, black/whitelist, source positions, pending replies). `Storage` already
   satisfies it. Add `InMemoryStore` in `tests/fakes.py` so handlers and filters can be tested
   without disk.

Not doing: DI containers, a repository layer, or splitting `views.py` page objects (they
already follow SRP).

## Steps (safe order: one branch and one commit each, phone smoke test between steps)

- **7a — Context, no handler changes (M).** Add `SourceContext` and
  `build_source_context`. Plugins build the context, then still call the old functions,
  passing the unpacked fields. This removes the duplication in plugins and doesn't touch
  handler logic.
- **7b — Handlers take `ctx` (M).** Change each `handle_*` signature to
  `(ctx, **specific)` and drop the fake `self`. Move one handler at a time, running the suite
  after each.
- **7c — Handler classes (M–L).** Move the functions into `core/sources/` classes, and pull
  the shared blocks into `SourceHandler`. Keep `handle_sources.py` as thin re-exports for one
  commit, then delete it.
- **7d — Storage protocol + fake (S).** Add `InteractionStore` and `InMemoryStore`. Type
  hint `SourceContext.storage` and `Filter.storage` against the protocol.

## Tests / smoke checks

- Before 7a: a characterization test with a fake device for `interact()` and the skip
  checks, so that 7b/7c can't change which users are skipped. (Uses `InMemoryStore`, so 7d's
  fake is written first, in the test folder only.)
- Per step: the full pytest suite, pyflakes, and an import check.
- Phone run per step (Pi): one session each of `blogger-followers`, `hashtag-likers`, and
  `interact-from-urls` (likers + commenters) at small limits. Compare the log with a
  pre-change run: same users skipped for the same reasons, PMs/greetings still sent,
  source positions resume.

## Decisions (Paul, 2026-09-22)

1. Four branches, 7a–7d, one per step.
2. `interact_feed` and `like_from_urls` move to the new context and handlers too.
3. Start 7a without waiting for the Gemini plan review (the quota is blocked). Rerun
   `/gemini-plan-review` when it's available.

## Review log

- Gemini plan review attempted 2026-09-22 and returned no answer (quota or rate limit).
  No findings yet.
