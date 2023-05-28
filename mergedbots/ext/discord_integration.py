# pylint: disable=no-name-in-module
"""Discord integration for MergedBots."""
import contextlib
import logging
import re
from typing import Any, AsyncGenerator

import discord
from pydantic import BaseModel, PrivateAttr

from mergedbots.core import MergedBot, MergedMessage, MergedUser
from mergedbots.errors import ErrorWrapper
from mergedbots.utils import get_text_chunks, format_error_with_full_tb

logger = logging.getLogger(__name__)

DISCORD_MSG_LIMIT = 1900


class MergedBotDiscord(BaseModel):
    """Integration of a merged bot with Discord."""

    bot: MergedBot

    _channel_conv_tails: dict[int, MergedMessage | None] = PrivateAttr(default_factory=dict)
    _users: dict[int, MergedUser] = PrivateAttr(default_factory=dict)

    def attach_discord_client(self, discord_client: discord.Client) -> None:
        """Attach a Discord client to a merged bot by its handle."""

        async def on_message(discord_message: discord.Message) -> None:
            """Called when a message is sent to a channel (both a user message and a bot message)."""
            if discord_message.author == discord_client.user:
                # make sure we are not embarking on an "infinite loop" journey
                return

            try:
                merged_user = self._users.get(discord_message.author.id)
                if not merged_user:
                    merged_user = MergedUser(name=discord_message.author.name)
                    self._users[discord_message.author.id] = merged_user

                message_visible_to_bots = True
                if discord_message.content.startswith("!"):
                    # any prefix command just starts a new conversation for now
                    # TODO rethink conversation restarts
                    self._channel_conv_tails[discord_message.channel.id] = None
                    message_visible_to_bots = False

                # TODO read about discord_message.channel.id... is it unique across all servers ?
                previous_msg = self._channel_conv_tails.get(discord_message.channel.id)

                user_message = MergedMessage(
                    previous_msg=previous_msg,
                    in_fulfillment_of=None,
                    sender=merged_user,
                    content=discord_message.content,
                    is_still_typing=False,
                    is_visible_to_bots=message_visible_to_bots,
                    originator=merged_user,
                )
                self._channel_conv_tails[discord_message.channel.id] = user_message

                async for bot_message in self._fulfill_message_with_typing(
                    message=user_message,
                    typing_context_manager=discord_message.channel.typing(),
                ):
                    for chunk in get_text_chunks(bot_message.content, DISCORD_MSG_LIMIT):
                        await discord_message.channel.send(chunk)

                    self._channel_conv_tails[discord_message.channel.id] = bot_message

            except Exception as exc:  # pylint: disable=broad-exception-caught
                if isinstance(exc, ErrorWrapper):
                    exc = exc.error
                logger.error("Error while processing a Discord message: %s", exc, exc_info=exc)
                for chunk in get_text_chunks(format_error_with_full_tb(exc), DISCORD_MSG_LIMIT):
                    await discord_message.channel.send(f"```\n{chunk}\n```")

        discord_client.event(on_message)

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


def escape_discord_markdown(text):
    """Helper function to escape Discord markdown characters."""
    # TODO is this function needed at all ? who is responsible for escaping markdown and when ?
    escape_chars = r"\*_`~"
    return re.sub(rf"([{re.escape(escape_chars)}])", r"\\\1", text)


_null_context = contextlib.nullcontext()
