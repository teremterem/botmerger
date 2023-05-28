# pylint: disable=no-name-in-module
"""Core logic of MergedBots library."""
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any
from typing import Callable, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr, UUID4, Field

from mergedbots.errors import BotHandleTakenError, BotNotFoundError
from mergedbots.utils import assert_correct_obj_type_or_none, generate_merged_bot_key, generate_merged_user_key

# TODO find a way to break this module down into submodules while avoiding circular imports

FulfillmentFunc = Callable[["MergedBot", "MergedMessage"], AsyncGenerator["MergedMessage", None]]


class ObjectManager(ABC, BaseModel):
    """An abstract object manager."""

    @abstractmethod
    def register_object(self, key: Any, value: Any) -> None:
        """Register an object."""

    @abstractmethod
    def get_object(self, key: Any) -> Any | None:
        """Get an object by its key."""

    def register_merged_object(self, obj: "MergedObject") -> None:
        """Register a merged object."""
        self.register_object(obj.uuid, obj)

    def get_merged_object(self, uuid: UUID4) -> "MergedObject | None":
        """Get a merged object by its uuid."""
        obj = self.get_object(uuid)
        assert_correct_obj_type_or_none(obj, MergedObject, uuid)
        return obj

    def register_bot(self, bot: "MergedBot") -> None:
        """Register a bot."""
        self.register_merged_object(bot)
        self.register_object(generate_merged_bot_key(bot.handle), bot)

    def get_bot(self, handle: str) -> "MergedBot | None":
        """Get a bot by its handle."""
        key = generate_merged_bot_key(handle)
        obj = self.get_object(key)
        assert_correct_obj_type_or_none(obj, MergedBot, key)
        return obj

    def find_or_create_user(self, channel_type: str, channel_specific_id: Any, user_display_name: str) -> "MergedUser":
        """Find or create a user."""
        key = generate_merged_user_key(channel_type=channel_type, channel_specific_id=channel_specific_id)
        user = self.get_object(key)
        assert_correct_obj_type_or_none(user, MergedUser, key)
        if user:
            return user

        user = MergedUser(
            uuid=uuid4(),
            bot_manager=self,
            name=user_display_name,
        )
        self.register_merged_object(user)
        self.register_object(key, user)
        return user


class InMemoryObjectManager(ObjectManager):
    """An in-memory object manager."""

    _objects: dict[Any, Any] = PrivateAttr(default_factory=dict)

    def register_object(self, key: Any, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    def get_object(self, key: Any) -> Any | None:
        """Get an object by its key."""
        return self._objects.get(key)


class BotManager(BaseModel):
    """An abstract factory of everything else in this library."""

    object_manager: ObjectManager = Field(default_factory=InMemoryObjectManager)

    def create_bot(self, handle: str, name: str = None, **kwargs) -> "MergedBot":
        """Create a merged bot."""
        if self.object_manager.get_bot(handle):
            raise BotHandleTakenError(f"bot with handle {handle!r} is already registered")

        if not name:
            name = handle
        bot = MergedBot(uuid=uuid4(), bot_manager=self, handle=handle, name=name, **kwargs)

        self.object_manager.register_bot(bot)
        return bot

    def find_bot(self, handle: str) -> "MergedBot":
        """Fetch a bot by its handle."""
        bot = self.object_manager.get_bot(handle)
        if not bot:
            raise BotNotFoundError(f"bot with handle {handle!r} does not exist")
        return bot

    def find_or_create_user(self, channel_type: str, channel_specific_id: Any, user_display_name: str) -> "MergedUser":
        """Find or create a user."""
        return self.object_manager.find_or_create_user(
            channel_type=channel_type,
            channel_specific_id=channel_specific_id,
            user_display_name=user_display_name,
        )


class MergedObject(BaseModel):
    """Base class for all MergedBots models."""

    uuid: UUID4
    bot_manager: BotManager

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
    is_still_typing: bool
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
