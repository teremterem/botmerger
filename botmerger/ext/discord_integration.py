# pylint: disable=no-name-in-module
"""Discord integration for MergedBots."""
import contextlib
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
            merged_channel = await bot.merger.find_or_create_user_channel(
                channel_type="discord",
                # TODO read about discord_message.channel.id - is it unique across all servers ?
                channel_id=discord_message.channel.id,
                user_display_name=discord_message.author.name,
            )

            # prefix_command = discord_message.content.startswith("!")
            # new_conversation = prefix_command

            user_request = await merged_channel.new_message_from_owner(discord_message.content)
            bot_responses = bot.trigger(user_request)

            async for response in _iterate_over_responses(bot_responses, discord_message.channel.typing()):
                for chunk in get_text_chunks(response.content, DISCORD_MSG_LIMIT):
                    await discord_message.channel.send(chunk)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error while processing a Discord message: %s", exc, exc_info=exc)
            for chunk in get_text_chunks(format_error_with_full_tb(exc), DISCORD_MSG_LIMIT):
                await discord_message.channel.send(f"```\n{chunk}\n```")

    discord_client.event(on_message)


async def _iterate_over_responses(
    bot_responses: BotResponses, typing_context_manager: Any
) -> AsyncGenerator[MergedMessage, None]:
    response = None
    while True:
        try:
            if not response or response.is_still_typing:
                _typing_context_manager = typing_context_manager
            else:
                _typing_context_manager = _null_context

            async with _typing_context_manager:
                response = await anext(bot_responses)

        except StopAsyncIteration:
            return

        yield response.message


_null_context = contextlib.nullcontext()