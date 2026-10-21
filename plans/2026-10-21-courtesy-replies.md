# Courtesy replies in reply-dms

## Goal
When someone answers with only a courtesy ("gracias", "qué chévere", 🔥), thank them back
instead of dropping them or sending a Slack alert. DeepSeek only detects it; the text comes
from templates in deepseek.yml (Paul's choice: templates, all three stages).

## Behavior
- Main question first, as today. Only when it isn't YES, ask DeepSeek a second question:
  "is this only a thank-you / compliment, without answering?".
- greeted + courtesy: send `thanks-messages`, keep waiting for a real yes/no.
- sent_youtube + courtesy: send `thanks-messages` + `soundcloud-question`, keep waiting.
- After the SoundCloud link: new stage `sent_soundcloud` instead of removing. If they reply:
  courtesy -> thank back once, done; anything else -> Slack (needs a human).
  Silent ones aren't opened (checked only when their thread is unread) and expire after 72 h.
  Expiry never touches a thread that is unread right now. Once their thread is opened they
  get `recheck` (it's read now) and are checked normally until the 72 h are up.
- A second courtesy in the same stage gets no new thank-you: the person is done (no loops).
- ERROR from DeepSeek on either question: keep in queue, as today.

## Files
- GramAddict/plugins/action_reply_dms.py
- tests/test_reply_decisions.py
- config-examples/deepseek.yml

## Checks
python -m pytest; pyflakes on changed files.
