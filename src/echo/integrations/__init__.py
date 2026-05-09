"""External channel integrations for PROJECT ECHO."""

from .telegram_bot import TelegramBotBridge
from .telegram_notify import send_goal_resolution_notification

__all__ = ["TelegramBotBridge", "send_goal_resolution_notification"]
