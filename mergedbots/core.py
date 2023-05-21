"""Core logic of MergedBots library."""
from typing import Callable, AsyncGenerator

from .models import MergedBot, MergedMessage, FulfillmentFunc


class BotMerger:
    """A manager of merged bots."""

    def __init__(self) -> None:
        self.merged_bots: dict[str, MergedBot] = {}

    def register_bot(
        self,
        handle: str,
        name: str = None,
        description: str = None,
    ) -> Callable[[FulfillmentFunc], FulfillmentFunc]:
        """A decorator that registers a fulfillment function as a MergedBot."""

        def decorator(fulfillment_func: FulfillmentFunc) -> FulfillmentFunc:
            self.merged_bots[handle] = MergedBot(
                handle=handle,
                name=name or handle,
                description=description,
                fulfillment_func=fulfillment_func,
            )
            return fulfillment_func

        return decorator

    async def fulfill_message(
        self,
        bot_handle: str,
        message: MergedMessage,
        fallback_bot_handle: str = None,
    ) -> AsyncGenerator[MergedMessage, None]:
        """Fulfill a message. Returns a generator that would yield zero or more responses to the message."""
        try:
            bot = self.merged_bots[bot_handle]
        except KeyError:
            if not fallback_bot_handle:
                raise
            bot = self.merged_bots[fallback_bot_handle]

        async for response in bot.fulfillment_func(bot, message):
            yield response
