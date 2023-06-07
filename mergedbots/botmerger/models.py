"""Models for the BotMerger library."""
from mergedbots.botmerger.base import MergedParticipant


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = False

    alias: str
    description: str = None
