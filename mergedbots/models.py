# pylint: disable=no-name-in-module
"""Models for the MergedBots library."""
from collections import defaultdict
from typing import Any
from typing import AsyncGenerator

from pydantic import PrivateAttr

from mergedbots.base import MergedObject, MergedParticipant, FulfillmentFunc


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

    # TODO get rid if these two attributes - this data should be retrieved from the underlying storage
    _responses: list["MergedMessage"] = PrivateAttr(default_factory=list)
    _responses_by_bots: dict[str, list["MergedMessage"]] = PrivateAttr(default_factory=lambda: defaultdict(list))

    @property
    def is_sent_by_originator(self) -> bool:
        """
        Check if this message was sent by the originator of the whole interaction. This will most likely be a user,
        but in some cases may also be another bot (if the interaction is some sort of "inner dialog" between bots).
        """
        return self.sender == self.originator

    async def get_full_conversion(self, include_invisible_to_bots: bool = False) -> list["MergedMessage"]:
        """Get the full conversation that up to this message (inclusively)."""
        return await self.manager.get_full_conversion(self, include_invisible_to_bots=include_invisible_to_bots)

    async def bot_response(
        self,
        bot: MergedBot,
        content: str,
        is_still_typing: bool,
        is_visible_to_bots: bool,
        **kwargs,
    ) -> "MergedMessage":
        """Create a bot response to this message."""
        return await self.manager.create_bot_response(
            bot=bot,
            in_fulfillment_of=self,
            content=content,
            is_still_typing=is_still_typing,
            is_visible_to_bots=is_visible_to_bots,
            **kwargs,
        )

    async def service_followup_for_user(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a service followup for the user."""
        return await self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=True,  # it's not the final bot response, more messages are expected
            is_visible_to_bots=False,  # service followups aren't meant to be interpreted by other bots
        )

    async def service_followup_as_final_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a service followup as the final response to the user."""
        return await self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=False,
            is_visible_to_bots=False,  # service followups aren't meant to be interpreted by other bots
        )

    async def interim_bot_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create an interim bot response to this message (which means there will be more responses)."""
        return await self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=True,  # there will be more messages
            is_visible_to_bots=True,
        )

    async def final_bot_response(
        self,
        bot: MergedBot,
        content: str,
    ) -> "MergedMessage":
        """Create a final bot response to this message."""
        return await self.bot_response(
            bot=bot,
            content=content,
            is_still_typing=False,
            is_visible_to_bots=True,
        )
