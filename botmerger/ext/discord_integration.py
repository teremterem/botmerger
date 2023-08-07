"""Discord integration for BotMerger."""
import contextlib
import json
import logging
from typing import Any, AsyncGenerator

import discord

from botmerger import MergedBot, BotResponses, MergedMessage
from botmerger.utils import get_text_chunks, format_error_with_full_tb

logger = logging.getLogger(__name__)

DISCORD_MSG_LIMIT = 1900


def attach_bot_to_discord(bot: MergedBot, discord_client: discord.Client) -> None:
    """Attach a bot to a Discord client."""

    async def on_message(discord_message: discord.Message) -> None:
        """Called when a message is sent to a channel (both a user message and a bot message)."""
        if discord_message.author == discord_client.user:
            # make sure we are not embarking on an infinite loop of responding to our own messages
            return

        try:
            channel_msg_ctx = await bot.merger.find_or_create_user_channel(
                channel_type="discord",
                channel_id=discord_message.channel.id,
                user_display_name=discord_message.author.name,
            )

            bot_responses = bot.trigger(
                discord_message.content,
                override_sender=channel_msg_ctx.sender,
                override_parent_ctx=channel_msg_ctx,
                # extra_fields={
                #     # TODO is this unsecure ? (given that MergedMessage objects will be passed around between
                #     #  BotMerger distributed nodes in the future)
                #     "discord_channel_id": discord_message.channel.id,
                #     "discord_message_id": discord_message.id,
                # },
            )

            async for response in _iterate_over_responses(bot_responses, discord_message.channel.typing()):
                response_content = response.content
                if not isinstance(response_content, str):
                    try:
                        response_content = f"```json\n{json.dumps(response_content, indent=2)}\n```"
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        logger.error("Error while formatting response content: %s", exc, exc_info=exc)

                for chunk in get_text_chunks(response_content, DISCORD_MSG_LIMIT):
                    await discord_message.channel.send(chunk)  # , reference=discord_message)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error while processing a Discord message: %s", exc, exc_info=exc)
            for chunk in get_text_chunks(format_error_with_full_tb(exc), DISCORD_MSG_LIMIT):
                await discord_message.channel.send(f"```\n{chunk}\n```")

    discord_client.event(on_message)


async def _iterate_over_responses(
    bot_responses: BotResponses, typing_context_manager: Any
) -> AsyncGenerator[MergedMessage, None]:
    resp_iterator = aiter(bot_responses)
    response = None

    while True:
        try:
            if not response or response.still_thinking:
                _typing_context_manager = typing_context_manager
            else:
                _typing_context_manager = _null_context

            async with _typing_context_manager:
                response = await anext(resp_iterator)

        except StopAsyncIteration:
            return

        yield response


_null_context = contextlib.nullcontext()
