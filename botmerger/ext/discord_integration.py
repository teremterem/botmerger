# pylint: disable=no-name-in-module
"""Discord integration for MergedBots."""
import contextlib
import logging
import re
from typing import Any, AsyncGenerator

import discord
from pydantic import BaseModel

from botmerger import MergedBot

logger = logging.getLogger(__name__)

DISCORD_MSG_LIMIT = 1900


def attach_bot_to_discord(bot: MergedBot, discord_client: discord.Client) -> None:
    async def on_message(discord_message: discord.Message) -> None:
        """Called when a message is sent to a channel (both a user message and a bot message)."""
        if discord_message.author == discord_client.user:
            # make sure we are not embarking on an infinite loop of responding to our own message
            return

        try:
            merged_channel = await bot.merger.find_or_create_user_channel(
                channel_type="discord",
                # TODO read about discord_message.channel.id... is it unique across all servers ?
                channel_id=discord_message.channel.id,
                user_display_name=discord_message.author.name,
            )

            # prefix_command = discord_message.content.startswith("!")
            # new_conversation = prefix_command

            user_message = await merged_channel.new_message_from_owner(
                channel_type="discord",
                content=discord_message.content,
            )

            async for bot_message in self._fulfill_message_with_typing(
                message=user_message,
                typing_context_manager=discord_message.channel.typing(),
            ):
                for chunk in get_text_chunks(bot_message.content, DISCORD_MSG_LIMIT):
                    await discord_message.channel.send(chunk)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            if isinstance(exc, ErrorWrapper):
                exc = exc.error
            logger.error("Error while processing a Discord message: %s", exc, exc_info=exc)
            for chunk in get_text_chunks(format_error_with_full_tb(exc), DISCORD_MSG_LIMIT):
                await discord_message.channel.send(f"```\n{chunk}\n```")

    # Attach the Discord client to the MergedBot.
    self.discord_client.event(on_message)


async def _fulfill_message_with_typing(
    self, message: MergedMessage, typing_context_manager: Any
) -> AsyncGenerator[MergedMessage, None]:
    """
    Fulfill a message. Returns a generator that would yield zero or more responses to the message.
    typing_context_manager is a context manager that would be used to indicate that the bot is typing.
    """
    response_generator = self.bot.fulfill(message)

    response = None
    while True:
        try:
            if not response or response.is_still_typing:
                _typing_context_manager = typing_context_manager
            else:
                _typing_context_manager = _null_context

            async with _typing_context_manager:
                response = await anext(response_generator)

        except StopAsyncIteration:
            return

        yield response


_null_context = contextlib.nullcontext()
