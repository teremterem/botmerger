# pylint: disable=no-name-in-module
"""Models for the BotMerger library."""
from collections import deque
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import Field, UUID4

from botmerger.base import (
    MergedObject,
    SingleTurnHandler,
    SingleTurnContext,
    BotResponses,
    MessageContent,
    MessageType,
    BaseMessage,
)


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None

    async def trigger(
        self,
        request: MessageType = None,
        sender: Optional["MergedParticipant"] = None,
        channel: Optional["MergedChannel"] = None,
        **kwargs,
    ) -> BotResponses:
        """
        Trigger this bot to respond to a message. Returns an object that can be used to retrieve the bot's
        response(s) in an asynchronous manner.
        """
        if sender is None:
            sender = SingleTurnContext.this_bot_context.get()
        if channel is None:
            channel = SingleTurnContext.channel_context.get()
        # if `request` is "plain" content, convert it to OriginalMessage, otherwise wrap it in ForwardedMessage
        request = await self.merger.create_message(
            thread_uuid=uuid4(),  # create a brand-new thread
            channel=channel,
            sender=sender,
            content=request,
            indicate_typing_afterwards=False,
            responds_to=None,
            goes_after=None,
            **kwargs,
        )
        return await self.merger.trigger_bot(self, request)

    async def get_final_response(
        self,
        request: MessageType = None,
        sender: Optional["MergedParticipant"] = None,
        channel: Optional["MergedChannel"] = None,
        **kwargs,
    ) -> Optional["MergedMessage"]:
        """Get the final response from the bot for a given request."""
        responses = await self.trigger(request, sender=sender, channel=channel, **kwargs)
        return await responses.get_final_response()

    def single_turn(self, handler: SingleTurnHandler) -> SingleTurnHandler:
        """
        A decorator that registers a local single-turn handler function for this MergedBot. Single-turn means that
        the function will be called as an event handler for a single incoming message (or a single set of messages
        if they were sent as a bundle).
        """
        self.merger.register_local_single_turn_handler(self, handler)
        return handler

    def __call__(self, handler: SingleTurnHandler) -> SingleTurnHandler:
        return self.single_turn(handler)


class MergedUser(MergedParticipant):
    """A user that can interact with bots."""

    is_human: bool = Field(True, const=True)


class MergedChannel(MergedObject):
    """A logical channel where interactions between two or more participants happen."""

    channel_type: str
    channel_id: Any
    owner: MergedParticipant

    async def next_message_from_owner(
        self,
        content: MessageContent,
        indicate_typing_afterwards: bool = False,
        responds_to: Optional["MergedMessage"] = None,
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a new message that goes after the last message in this channel. Mark it as if it was sent by the
        owner of the channel.
        """
        return await self.next_message(
            sender=self.owner,
            content=content,
            indicate_typing_afterwards=indicate_typing_afterwards,
            responds_to=responds_to,
            **kwargs,
        )

    async def next_message(
        self,
        sender: MergedParticipant,
        content: MessageContent,
        indicate_typing_afterwards: bool = False,
        responds_to: Optional["MergedMessage"] = None,
        **kwargs,
    ) -> "MergedMessage":
        """Create a new message that goes after the last message in this channel."""
        return await self.merger.create_next_message(
            thread_uuid=self.uuid,  # in this case, the thread is the channel itself
            channel=self,
            sender=sender,
            content=content,
            indicate_typing_afterwards=indicate_typing_afterwards,
            responds_to=responds_to,
            **kwargs,
        )


class MergedMessage(BaseMessage, MergedObject):
    """A message that was sent in a channel."""

    channel: MergedChannel
    thread_uuid: UUID4  # TODO should this be a dedicated MergedThread class ?
    sender: MergedParticipant
    indicate_typing_afterwards: bool
    responds_to: Optional["MergedMessage"]
    goes_after: Optional["MergedMessage"]

    def __enter__(self) -> "MergedMessage":
        """Set this message as the current context."""
        try:
            previous_msg_token_stack = self._previous_msg_token_stack.get()
        except LookupError:
            previous_msg_token_stack = deque()
            self._previous_msg_token_stack.set(previous_msg_token_stack)

        previous_msg_token = self.current_msg_context.set(self)  # <- this is the context switch
        previous_msg_token_stack.append(previous_msg_token)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Restore the message that was the current context before this one."""
        previous_msg_token = self._previous_msg_token_stack.get().pop()
        self.current_msg_context.reset(previous_msg_token)


class OriginalMessage(MergedMessage):
    """This subclass represents an original message. It implements `content` as a Pydantic field."""

    content: Union[str, Any]

    @property
    def original_sender(self) -> MergedParticipant:
        """For an original message, the original sender is the same as the sender."""
        return self.sender


class ForwardedMessage(MergedMessage):
    """
    This subclass represents a forwarded message. It implements `content` as a property that is delegated to the
    original message.
    """

    original_message: OriginalMessage

    @property
    def original_sender(self) -> MergedParticipant:
        """The original sender of the forwarded message."""
        return self.original_message.sender

    @property
    def content(self) -> MessageContent:
        """The content of the original message."""
        return self.original_message.content
