# pylint: disable=no-name-in-module
"""Models for the MergedBots library."""
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any
from typing import Callable, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr, UUID4, Field

# TODO recursively freeze all the MergedObject instances together with their contents after they are created

FulfillmentFunc = Callable[["MergedBot", "MergedMessage"], AsyncGenerator["MergedMessage", None]]


class BotManager(BaseModel, ABC):
    """An abstract factory of everything else in this library."""

    @abstractmethod
    def fulfill(self, bot_handle: str, request: "MergedMessage") -> AsyncGenerator["MergedMessage", None]:
        """Find a bot by its handle and fulfill the request using that bot."""

    @abstractmethod
    def create_bot(self, handle: str, name: str = None, **kwargs) -> "MergedBot":
        """Create a merged bot."""

    @abstractmethod
    def find_bot(self, handle: str) -> "MergedBot":
        """Fetch a bot by its handle."""

    @abstractmethod
    def find_or_create_user(
        self, channel_type: str, channel_specific_id: Any, user_display_name: str, **kwargs
    ) -> "MergedUser":
        """Find or create a user."""

    @abstractmethod
    def create_originator_message(  # pylint: disable=too-many-arguments
        self,
        channel_type: str,
        channel_id: Any,
        originator: "MergedParticipant",
        content: str,
        is_visible_to_bots: bool = True,
        new_conversation: bool = False,
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a new message from the conversation originator. The originator is typically a human user, but in
        certain scenarios it can also be another bot.
        """


class MergedObject(BaseModel):
    """Base class for all MergedBots models."""

    # TODO how to prevent library consumers from instantiating these models directly ?

    manager: BotManager
    uuid: UUID4 = Field(default_factory=uuid4)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        """Check if two models represent the same concept."""
        if not isinstance(other, MergedObject):
            return False
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        """Get the hash of the model's uuid."""
        # TODO are we sure we don't want to keep these models non-hashable (pydantic default) ?
        return hash(self.uuid)


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = False

    handle: str
    description: str = None
    _fulfillment_func: FulfillmentFunc = PrivateAttr(default=None)

    async def fulfill(self, request: "MergedMessage") -> AsyncGenerator["MergedMessage", None]:
        """Fulfill a message."""
        async for response in self.manager.fulfill(self.handle, request):
            yield response

    def __call__(self, fulfillment_func: FulfillmentFunc) -> FulfillmentFunc:
        """A decorator that registers a local fulfillment function for this MergedBot."""
        self._fulfillment_func = fulfillment_func
        fulfillment_func.merged_bot = self
        return fulfillment_func


class MergedUser(MergedParticipant):
    """A user that can interact with bots."""

    is_human: bool = True


class MergedMessage(MergedObject):
    """A message that can be sent by a bot or a user."""

    # TODO convert these two fields into a model of their own ?
    channel_type: str
    channel_id: Any

    sender: MergedParticipant
    content: str
    is_visible_to_bots: bool

    is_still_typing: bool  # TODO move this out into some sort of wrapper

    originator: MergedParticipant
    previous_msg: "MergedMessage | None"
    in_fulfillment_of: "MergedMessage | None"

    _responses: list["MergedMessage"] = PrivateAttr(default_factory=list)
    _responses_by_bots: dict[str, list["MergedMessage"]] = PrivateAttr(default_factory=lambda: defaultdict(list))

    @property
    def is_sent_by_originator(self) -> bool:
        """
        Check if this message was sent by the originator of the whole interaction. This will most likely be a user,
        but in some cases may also be another bot (if the interaction is some sort of "inner dialog" between bots).
        """
        return self.sender == self.originator

    def get_full_conversion(self, include_invisible_to_bots: bool = False) -> list["MergedMessage"]:
        """Get the full conversation that this message is a part of."""
        raise ValueError("Redo via BotManager")  # TODO
        conversation = []
        msg = self
        while msg:
            if include_invisible_to_bots or msg.is_visible_to_bots:
                conversation.append(msg)
            msg = msg.previous_msg

        conversation.reverse()
        return conversation

    def bot_response(
        self,
        bot: MergedBot,
        content: str,
        is_still_typing: bool,
        is_visible_to_bots: bool,
    ) -> "MergedMessage":
        """Create a bot response to this message."""
        previous_msg = self._responses[-1] if self._responses else self
        response_msg = MergedMessage(
            previous_msg=previous_msg,
            in_fulfillment_of=self,
            sender=bot,
            content=content,
            is_still_typing=is_still_typing,
            is_visible_to_bots=is_visible_to_bots,
            originator=self.originator,
        )
        self._responses.append(response_msg)
        # TODO what if message processing failed and bot response list is not complete ?
        #  we need a flag to indicate that the bot response list is complete
        self._responses_by_bots[bot.handle].append(response_msg)
        return response_msg

    def service_followup_for_user(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a service followup for the user."""
        return self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=True,  # it's not the final bot response, more messages are expected
            is_visible_to_bots=False,  # service followups aren't meant to be interpreted by other bots
        )

    def service_followup_as_final_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a service followup as the final response to the user."""
        return self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=False,
            is_visible_to_bots=False,  # service followups aren't meant to be interpreted by other bots
        )

    def interim_bot_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create an interim bot response to this message (which means there will be more responses)."""
        return self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=True,  # there will be more messages
            is_visible_to_bots=True,
        )

    def final_bot_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a final bot response to this message."""
        return self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=False,
            is_visible_to_bots=True,
        )
