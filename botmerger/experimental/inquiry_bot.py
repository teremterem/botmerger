# TODO is inquiry_bot a good name for this ?
from botmerger import MergedBot, SingleTurnContext


def create_inquiry_bot(target_bot: MergedBot) -> MergedBot:
    # TODO turn this function into a class ?
    @target_bot.merger.create_bot("inquiry_bot")  # TODO should the alias be customizable ?
    async def _inquiry_bot(context: SingleTurnContext) -> None:
        await context.yield_from(await target_bot.trigger(context.request))

    return _inquiry_bot.bot
