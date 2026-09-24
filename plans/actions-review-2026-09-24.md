# Actions review — what works on Instagram 300 and what's worth using (2026-09-24)

Goal: get your DJ mixes heard by people in Peru's club scene, turning Instagram contacts into
listeners (YouTube, then SoundCloud).

**Evidence levels:**
- **Proven:** the Pi logs show the job doing real work (all `logs/*.log`, since April).
- **Broken:** the logs or code show it failing.
- **Unverified:** the job never ran on this phone; its screens need a check on Instagram
  300.0.0.29.110.

## 1. Jobs you use today (Pi log history)

| Job | Runs / days | Result | Status |
|---|---|---|---|
| `blogger-followers` | 29 / 15 | 1,708 profiles interacted, 51 greetings | **Proven** |
| `blogger-post-likers` | 26 / 18 | 2,157 profiles interacted, 117 greetings | **Proven**: your best source (warmer people, more greetings) |
| `reply-dms` | 13 / 2 | 38 links sent (YouTube + SoundCloud) | **Proven** since 2026-09-23 |
| `unfollow` | 27 / 14 | **33 unfollows out of 273 attempts** | **Broken**: 262 of 273 end in "Could not find @user in search" |
| `blogger` | 5 / 3 | 11 interactions | Proven, but low value (see below) |

**Why `unfollow` fails:**
1. It searches each username.
2. When the account isn't in the top suggestions, it taps "See all results" and looks for an
   **Accounts** tab (`fixed_tabbar_tabs_container` / `tab_button_name_text`). No
   "Switching to ACCOUNTS" line is ever logged, so that tab isn't found on Instagram 300.
3. `reply-dms` uses the same search but works, because the people it opens were messaged
   recently and show up in the top suggestions.

The same tab lookup is used by `hashtag-*`, `place-*` and every "search then open" job, so
fixing it matters beyond unfollow.

## 2. All 28 jobs: can it work today, and is it useful to you?

**Usefulness scale:**
- ★★★ core for your goal
- ★★ useful sometimes
- ★ little value for you
- ✗ not relevant

### Finding people (outreach)

| Job | What it does | Works on IG 300? | Useful? |
|---|---|---|---|
| `blogger-followers` | Followers of club accounts | **Proven** | ★★★ Club followers are your audience |
| `blogger-post-likers` | Likers of a club's latest posts | **Proven** | ★★★ Warmer than followers: they engage now |
| `post-likers-commenters-from-file` | Likers + commenters of specific post URLs (e.g. a party flyer) | Unverified (opens posts by URL, which works for reply-dms) | ★★★ Point it at event posts of clubs you play or want to play; commenters are the warmest people |
| `blogger-following` | Accounts a blogger follows | Unverified (same screen type as followers, likely works) | ★★ Use on a DJ or promoter's following to find venues, promoters and other DJs, not listeners |
| `hashtag-likers-top` / `hashtag-posts-top` | Likers / owners of top posts for a hashtag | Unverified: needs the Tags search tab | ★★ `#reggaetonlima`, `#discotecaslima` type tags; broader and colder than clubs |
| `hashtag-likers-recent` / `hashtag-posts-recent` | Same, "Recent" tab | Likely **broken**: needs a "Recent" tab on hashtag pages | ★★ if it worked |
| `place-likers-*` / `place-posts-*` | Likers / owners of posts tagged at a location | You report these don't work; needs the Places search tab | ★★★ in theory (people who posted *at the club*), if it can be fixed |
| `interact-from-file` | Interact with usernames from a file | Unverified (uses the same search as unfollow, so likely hit by the Accounts-tab bug) | ★★ Good for curated lists |
| `blogger` | Interact with the club's own profile | Proven | ★ Greetings to bloggers are blocked on purpose; only likes/follows |
| `feed` | Interact with your own home feed | Unverified | ✗ People you already follow |

### Conversation and follow-up

| Job | What it does | Works? | Useful? |
|---|---|---|---|
| `reply-dms` | Reads replies, sends the YouTube then SoundCloud link | **Proven** | ★★★ This is where listeners are won |

### Account hygiene

| Job | What it does | Works? | Useful? |
|---|---|---|---|
| `unfollow` | Unfollow people the bot followed, after `unfollow-delay` days | **Broken** (search) | ★★★ Keeps your following count sane; needs the fix |
| `unfollow-non-followers` | Same, only those who don't follow back | Unverified (uses your following list, not search) | ★★ Alternative while search is broken |
| `unfollow-any-non-followers` | Anyone who doesn't follow back | Unverified | ★ Can unfollow people you followed by hand |
| `unfollow-any-followers` / `unfollow-any` | Unfollow followers / anyone | Unverified | ✗ Risky: removes real contacts |
| `unfollow-least-interacted` | Uses Instagram's "Least interacted with" list | Unverified (depends on that category existing) | ★ |
| `unfollow-from-file` | Unfollow usernames from a file | Unverified (search) | ★ |
| `remove-followers-from-file` | Remove followers listed in a file | Unverified | ✗ |
| `posts-from-file` (like-from-urls) | Like specific posts by URL | Unverified | ★ E.g. like a club's event posts |

### Reporting

| Job | What it does | Works? | Useful? |
|---|---|---|---|
| `slack-reports` | Session report to Slack | Works (Slack alerts are delivered) | ★★ You already use Slack for handoffs |
| `telegram-reports` | Same, to Telegram | Unverified | ✗ if you use Slack |
| `analytics` | PDF report of sessions | Unverified (needs matplotlib) | ★ |

## 3. What to check on the phone (read-only screen dumps, ~10 minutes, bot idle)

1. **Search results tabs:** search a common word, tap "See all results", and dump. Does the
   tab row exist, and what are its ids and names ("Accounts", "Tags", "Places")? This
   decides unfollow, interact-from-file, hashtag and place jobs.
2. **Hashtag page:** open `#reggaeton` and dump. Is there a "Top" / "Recent" switch?
3. **Place page:** open a club's location and dump. Is there a "Top" / "Recent" switch, and
   a post grid?
4. **Following list:** dump your own following list. Is "Least interacted with" there?
5. **Likers list of a post:** already proven by `blogger-post-likers`.

## 4. Recommendation

1. **Fix the search tab lookup first.** It unblocks `unfollow` (your following count only
   grows today) and probably `interact-from-file`, hashtags and places.
2. **Add `post-likers-commenters-from-file`** with event posts of your target clubs: the
   warmest audience after replies.
3. **Keep** `blogger-post-likers` > `blogger-followers`: post-likers get a greeting in 5.4% of
   interactions (117 / 2,157), followers in 3.0% (51 / 1,708).
4. **Places:** worth fixing only if the probe shows the location pages still have a usable
   post grid; people who posted at the club are the ideal audience.
5. **Drop** `blogger` (little value), `feed`, and the `unfollow-any*` variants.
