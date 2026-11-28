"""Temporary reminder mailer for Schedule.

The real Part 1 mailer must replace this stub with the same public signatures.
"""


class MailError(Exception):
    """A reminder email could not be sent."""


def send_reminder(
    to: str,
    occurrence: dict,
    display_name: str | None,
) -> None:
    """Stub: reminder delivery is implemented by Part 1."""
