import asyncio
from typing import AsyncGenerator

from pydantic import PrivateAttr

from mergedbots import MergedObject, MergedBot, MergedMessage, BotManager

_SEQUENCE_ENDED_SENTINEL = object()


class TwoWayBotWrapper(MergedObject):
    # TODO this is a draft implementation - to be refactored

    manager: BotManager
    this_bot_handle: str
    target_bot_handle: str
    feedback_bot_handle: str
    this_bot: MergedBot = None

    _inbound_queue: asyncio.Queue[MergedMessage] = PrivateAttr(default_factory=asyncio.Queue)
    _outbound_queue: asyncio.Queue[MergedMessage | object] = PrivateAttr(default_factory=asyncio.Queue)
    _bot_started: bool = PrivateAttr(default=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.this_bot = self.manager.create_bot(self.this_bot_handle)
        self.this_bot(self.fulfill_this_bot)

    async def run_target_bot(self) -> None:
        while True:
            request = await self._inbound_queue.get()
            async for response in self.manager.fulfill(self.target_bot_handle, request):
                await self._outbound_queue.put(response)
            await self._outbound_queue.put(_SEQUENCE_ENDED_SENTINEL)

    async def fulfill_this_bot(
        self, this_bot: MergedBot, message: MergedMessage
    ) -> AsyncGenerator[MergedMessage, None]:
        if not self._bot_started:
            self._bot_started = True
            asyncio.create_task(self.run_target_bot())

        await self._inbound_queue.put(message)
        while response := await self._outbound_queue.get():
            if response is _SEQUENCE_ENDED_SENTINEL:
                return
            yield response
