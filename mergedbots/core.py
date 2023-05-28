# pylint: disable=no-name-in-module
"""Core logic of MergedBots library."""
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any
from typing import Callable, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr, UUID4, Field

from mergedbots.errors import BotHandleTakenError, BotNotFoundError

# TODO find a way to break this module down into submodules while avoiding circular imports
# TODO freeze all the MergedObjects after they are created (including their contents)

FulfillmentFunc = Callable[["MergedBot", "MergedMessage"], AsyncGenerator["MergedMessage", None]]
ObjectKey = Any | tuple[Any, ...]


class BotManager(ABC, BaseModel):
    """An abstract factory of everything else in this library."""

    # TODO think about thread-safety ?

    def create_bot(self, handle: str, name: str = None, **kwargs) -> "MergedBot":
        """Create a merged bot."""
        if self._get_bot(handle):
            raise BotHandleTakenError(f"bot with handle {handle!r} is already registered")

        if not name:
            name = handle
        bot = MergedBot(uuid=uuid4(), bot_manager=self, handle=handle, name=name, **kwargs)

        self._register_bot(bot)
        return bot

    def find_bot(self, handle: str) -> "MergedBot":
        """Fetch a bot by its handle."""
        bot = self._get_bot(handle)
        if not bot:
            raise BotNotFoundError(f"bot with handle {handle!r} does not exist")
        return bot

    def find_or_create_user(
        self,
        channel_type: str,
        channel_specific_id: Any,
        user_display_name: str,
        **kwargs,
    ) -> "MergedUser":
        """Find or create a user."""
        key = self._generate_merged_user_key(channel_type=channel_type, channel_specific_id=channel_specific_id)
        user = self._get_object(key)
        self._assert_correct_obj_type_or_none(user, MergedUser, key)
        if user:
            return user

        user = MergedUser(uuid=uuid4(), bot_manager=self, name=user_display_name, **kwargs)
        self._register_merged_object(user)
        self._register_object(key, user)
        return user

    def new_message_from_originator(  # pylint: disable=too-many-arguments
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
        conv_tail_key = self._generate_conversation_tail_key(
            channel_type=channel_type,
            channel_id=channel_id,
        )
        previous_msg = None if new_conversation else self._get_object(conv_tail_key)
        self._assert_correct_obj_type_or_none(previous_msg, MergedMessage, conv_tail_key)

        message = MergedMessage(
            uuid=uuid4(),
            bot_manager=self,
            previous_msg=previous_msg,
            in_fulfillment_of=None,
            sender=originator,
            content=content,
            is_still_typing=False,  # TODO use a wrapper object for this
            is_visible_to_bots=is_visible_to_bots,
            originator=originator,
            **kwargs,
        )
        self._register_merged_object(message)
        self._register_object(conv_tail_key, message)  # save the tail of the conversation
        return message

    @abstractmethod
    def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""

    @abstractmethod
    def _get_object(self, key: ObjectKey) -> Any | None:
        """Get an object by its key."""

    def _register_merged_object(self, obj: "MergedObject") -> None:
        """Register a merged object."""
        self._register_object(obj.uuid, obj)

    def _get_merged_object(self, uuid: UUID4) -> "MergedObject | None":
        """Get a merged object by its uuid."""
        obj = self._get_object(uuid)
        self._assert_correct_obj_type_or_none(obj, MergedObject, uuid)
        return obj

    def _register_bot(self, bot: "MergedBot") -> None:
        """Register a bot."""
        self._register_merged_object(bot)
        self._register_object(self._generate_merged_bot_key(bot.handle), bot)

    def _get_bot(self, handle: str) -> "MergedBot | None":
        """Get a bot by its handle."""
        key = self._generate_merged_bot_key(handle)
        bot = self._get_object(key)
        self._assert_correct_obj_type_or_none(bot, MergedBot, key)
        return bot

    # noinspection PyMethodMayBeStatic
    def _generate_merged_bot_key(self, handle: str) -> tuple[str, str]:
        """Generate a key for a bot."""
        return "bot_by_handle", handle

    # noinspection PyMethodMayBeStatic
    def _generate_merged_user_key(self, channel_type: str, channel_specific_id: Any) -> tuple[str, str, str]:
        """Generate a key for a user."""
        return "user_by_channel", channel_type, channel_specific_id

    # noinspection PyMethodMayBeStatic
    def _generate_conversation_tail_key(self, channel_type: str, channel_id: Any) -> tuple[str, str, str]:
        """Generate a key for a conversation tail."""
        return "conv_tail_by_channel", channel_type, channel_id

    # noinspection PyMethodMayBeStatic
    def _assert_correct_obj_type_or_none(self, obj: Any, expected_type: type, key: Any) -> None:
        """Assert that the object is of the expected type or None."""
        if obj and not isinstance(obj, expected_type):
            raise TypeError(
                f"wrong type of object by the key {key!r}: "
                f"expected {expected_type.__name__!r}, got {type(obj).__name__!r}",
            )


class InMemoryBotManager(BotManager):
    """An in-memory object manager."""

    _objects: dict[ObjectKey, Any] = PrivateAttr(default_factory=dict)

    def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    def _get_object(self, key: ObjectKey) -> Any | None:
        """Get an object by its key."""
        return self._objects.get(key)


class MergedObject(BaseModel):
    """Base class for all MergedBots models."""

    uuid: UUID4
    bot_manager: BotManager
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
    fulfillment_func: FulfillmentFunc = None

    async def fulfill(self, message: "MergedMessage") -> AsyncGenerator["MergedMessage", None]:
        """Fulfill a message."""
        async for response in self.fulfillment_func(self, message):
            yield response

    def __call__(self, fulfillment_func: FulfillmentFunc) -> FulfillmentFunc:
        """A decorator that registers a fulfillment function for the MergedBot."""
        self.fulfillment_func = fulfillment_func
        fulfillment_func.merged_bot = self
        return fulfillment_func


class MergedUser(MergedParticipant):
    """A user that can interact with bots."""

    is_human: bool = True


class MergedMessage(MergedObject):
    """A message that can be sent by a bot or a user."""

    sender: MergedParticipant
    content: str
    is_still_typing: bool  # TODO move this out into some sort of wrapper
    is_visible_to_bots: bool

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
