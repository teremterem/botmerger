from typing import AsyncGenerator

from mergedbots import MergedObject, MergedBot, MergedMessage, BotManager


class TwoWayBotWrapper(MergedObject):
    manager: BotManager
    this_bot_handle: str
    target_bot_handle: str
    feedback_bot_handle: str
    this_bot: MergedBot = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.this_bot = self.manager.create_bot(self.this_bot_handle)
        self.this_bot(self.target_bot_proxy)

    async def target_bot_proxy(
        self, this_bot: MergedBot, message: MergedMessage
    ) -> AsyncGenerator[MergedMessage, None]:
        target_bot = await self.manager.find_bot(self.target_bot_handle)
        async for response in target_bot.fulfill(message):
            yield await message.interim_bot_response(this_bot, "yo")
            yield response
