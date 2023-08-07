# TODO is inquiry_bot a good name for this ?
from botmerger.base import SingleTurnContext
from botmerger.models import MergedBot


def create_inquiry_bot(target_bot: MergedBot) -> MergedBot:
    # TODO turn this function into a class ?
    @target_bot.merger.create_bot("inquiry_bot")  # TODO should the alias be customizable ?
    async def _inquiry_bot(context: SingleTurnContext) -> None:
        await context.yield_from(target_bot.trigger(requests=context.requests))

    return _inquiry_bot.bot
