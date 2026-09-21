import logging
from datetime import datetime

from colorama import Fore, Style

from GramAddict.core.plugin_loader import Plugin
from GramAddict.core.slack import load_slack_config, slack_send_text
from GramAddict.plugins.telegram import (
    _calculate_session_duration,
    daily_summary,
    generate_report,
    load_sessions,
    weekly_average,
)

logger = logging.getLogger(__name__)


class SlackReports(Plugin):
    """Generate reports at the end of the session and send them using Slack"""

    def __init__(self):
        super().__init__()
        self.description = (
            "Generate reports at the end of the session and send them using Slack. "
            "You have to configure 'slack.yml' (with 'slack-webhook-url') in your account folder"
        )
        self.arguments = [
            {
                "arg": "--slack-reports",
                "help": "at the end of every session send a report to your Slack channel",
                "action": "store_true",
                "operation": True,
            }
        ]

    def run(self, config, plugin, followers_now, following_now, time_left):
        username = config.args.username
        if username is None:
            logger.error("You have to specify a username for getting reports!")
            return

        sessions = load_sessions(username)
        if not sessions:
            logger.error(
                f"No session data found for {username}. Skipping report generation."
            )
            return

        last_session = sessions[-1]
        last_session["duration"] = _calculate_session_duration(last_session)

        slack_config = load_slack_config(username)
        if not slack_config:
            logger.error(
                f"No slack configuration found for {username}. Skipping report generation."
            )
            return

        daily_aggregated_data = daily_summary(sessions)
        today_data = daily_aggregated_data.get(last_session["start_time"][:10], {})
        today = datetime.now()
        weekly_average_data = weekly_average(daily_aggregated_data, today)
        report = generate_report(
            username,
            last_session,
            today_data,
            weekly_average_data,
            followers_now,
            following_now,
        )
        if slack_send_text(slack_config.get("slack-webhook-url"), report):
            logger.info(
                "Slack message sent successfully.",
                extra={"color": f"{Style.BRIGHT}{Fore.BLUE}"},
            )
        else:
            logger.error("Failed to send Slack message.")
