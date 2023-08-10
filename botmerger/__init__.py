"""
BotMerger is a library for merging multiple bots into a single bot.
"""
from botmerger.base import BotMerger, MergedObject, BotResponses, SingleTurnContext, MessageContent
from botmerger.mergers import InMemoryBotMerger, YamlLogBotMerger
from botmerger.models import MergedParticipant, MergedBot, MergedUser, MergedMessage, OriginalMessage, ForwardedMessage

__all__ = [
    "BotMerger",
    "BotResponses",
    "ForwardedMessage",
    "InMemoryBotMerger",
    "MergedBot",
    "MergedMessage",
    "MergedObject",
    "MergedParticipant",
    "MergedUser",
    "MessageContent",
    "OriginalMessage",
    "SingleTurnContext",
    "YamlLogBotMerger",
]
