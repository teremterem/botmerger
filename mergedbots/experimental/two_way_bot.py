import asyncio
from typing import AsyncGenerator

from pydantic import PrivateAttr, BaseModel

from mergedbots import MergedObject, MergedBot, MergedMessage, BotManager

_SEQUENCE_ENDED_SENTINEL = object()


class ChannelMediator(BaseModel):
    two_way_wrapper: "TwoWayBotWrapper"

    _human_to_bot_queue: asyncio.Queue[MergedMessage | object] = PrivateAttr(default_factory=asyncio.Queue)
    _bot_to_human_queue: asyncio.Queue[MergedMessage | object] = PrivateAttr(default_factory=asyncio.Queue)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        asyncio.create_task(self.run())

    async def run(self) -> None:
        while True:
            request = await self._human_to_bot_queue.get()
            async for response in self.two_way_wrapper.manager.fulfill(
                self.two_way_wrapper.target_bot_handle, request
            ):
                await self._bot_to_human_queue.put(response)
            await self._bot_to_human_queue.put(_SEQUENCE_ENDED_SENTINEL)
        # TODO don't do infinite loop, but rather delete the ChannelMediator from TwoWayBotWrapper
        #  when both queues are empty - this will memory-leak-proof the TwoWayBotWrapper


class TwoWayBotWrapper(MergedObject):
    manager: BotManager

    this_bot_handle: str
    target_bot_handle: str
    feedback_bot_handle: str

    this_bot: MergedBot = None
    feedback_bot: MergedBot = None

    _channel_mediators: dict[tuple[str, str], ChannelMediator] = PrivateAttr(default_factory=dict)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.this_bot = self.manager.create_bot(self.this_bot_handle)
        self.this_bot.low_level(self.fulfill_this_bot)

        self.feedback_bot = self.manager.create_bot(self.feedback_bot_handle)
        self.feedback_bot.low_level(self.fulfill_feedback_bot)

    async def fulfill_this_bot(
        self, this_bot: MergedBot, message: MergedMessage
    ) -> AsyncGenerator[MergedMessage, None]:
        channel_mediator = self._channel_mediators.get((message.channel_type, message.channel_id))
        if not channel_mediator:
            channel_mediator = ChannelMediator(two_way_wrapper=self)
            self._channel_mediators[(message.channel_type, message.channel_id)] = channel_mediator

        await channel_mediator._human_to_bot_queue.put(message)
        while response := await channel_mediator._bot_to_human_queue.get():
            if response is _SEQUENCE_ENDED_SENTINEL:
                return
            yield response

    async def fulfill_feedback_bot(
        self, feedback_bot: MergedBot, message: MergedMessage
    ) -> AsyncGenerator[MergedMessage, None]:
        channel_type = message.custom_fields["channel_type"]
        channel_id = message.custom_fields["channel_id"]
        channel_mediator = self._channel_mediators[(channel_type, channel_id)]

        # right now the problem is that fulfill_feedback_bot() may start competing with ChannelMediator.run() for
        # inbound messages - come up with a way to solve it
        # TODO push some kind of special object into _human_to_bot_queue to take over from ChannelMediator.run()
        await channel_mediator._bot_to_human_queue.put(message)
        yield await channel_mediator._human_to_bot_queue.get()


ChannelMediator.update_forward_refs()
