"""MergedBots package."""
from .core import BotMerger, FulfillmentFunc, MergedMessage, MergedBot
from .errors import MergedBotsError, ErrorWrapper

__all__ = [
    "BotMerger",
    "ErrorWrapper",
    "FulfillmentFunc",
    "MergedBot",
    "MergedBotsError",
    "MergedMessage",
]
