# pylint: disable=no-name-in-module
"""Base classes for the BotMerger library."""
from abc import ABC, abstractmethod
from asyncio import Queue
from copy import copy
from typing import Any, TYPE_CHECKING, Optional, Dict, Callable, Awaitable, Union, List
from uuid import uuid4

from pydantic import BaseModel, UUID4, Field

from botmerger.errors import ErrorWrapper

if TYPE_CHECKING:
    from botmerger.models import MergedBot, MergedChannel, MergedMessage, MessageEnvelope, MergedParticipant

SingleTurnHandler = Callable[["SingleTurnContext"], Awaitable[None]]
MessageContent = Union[str, Any]
MessageType = Union["MessageEnvelope", "MergedMessage", MessageContent]


class BotMerger(ABC):
    """
    An abstract factory of everything else in this library and also the low level implementation of everything else
    in this library. Almost all the methods of almost all the other classes in this library are just a facade for
    methods of this class.
    """

    @abstractmethod
    def trigger_bot(self, bot: "MergedBot", request: "MergedMessage") -> "BotResponses":
        """Find a bot by its alias and trigger it with a request."""

    @abstractmethod
    def create_bot(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> "MergedBot":
        """
        Create a bot. This version of bot creation function is meant to be called outside an async context (for ex.
        as a decorator to single-turn and multi-turn handler functions).
        """

    @abstractmethod
    async def create_bot_async(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> "MergedBot":
        """Create a bot while inside an async context."""

    @abstractmethod
    def register_local_single_turn_handler(self, bot: "MergedBot", handler: SingleTurnHandler) -> None:
        """Register a local function as a single turn handler for a bot."""

    @abstractmethod
    async def find_bot(self, alias: str) -> "MergedBot":
        """Fetch a bot by its alias."""

    @abstractmethod
    async def find_or_create_user_channel(
        self,
        channel_type: str,
        channel_id: Any,
        user_display_name: str,
        **kwargs,
    ) -> "MergedChannel":
        """
        Find or create a channel with a user as its owner. Parameters `channel_type` and `channel_specific_id` are
        used to look up the channel. Parameter `user_display_name` is used to create a user if the channel does not
        exist and is ignored if the channel already exists.
        """

    @abstractmethod
    async def create_message(
        self, channel: "MergedChannel", sender: "MergedParticipant", content: "MessageContent", **kwargs
    ) -> "MergedMessage":
        """Create a new message in a given channel."""


class MergedObject(BaseModel):
    """
    Base class for all BotMerger models. All the child classes of this class are meant to be immutable. Whatever
    mutable state one needs to associate with these objects should not be stored in the objects directly. Instead,
    such state should be stored at and dynamically looked up via BotMerger instance these objects belong to. This
    should simplify implementation of a distributed deployment of a network of BotMerger instances each with their
    own bots and which interact with each other.

    ATTENTION! Models inheriting from this class should not be instantiated directly. Use the factory methods of
    `BotMerger` instead.
    """

    class Config(BaseModel.Config):
        """
        ATTENTION AGAIN! If you define a new config for a model inheriting from this class, make sure to inherit from
        this config as well.
        """

        allow_mutation = False
        copy_on_model_validation = "none"
        arbitrary_types_allowed = True

    merger: BotMerger
    uuid: UUID4 = Field(default_factory=uuid4)
    # TODO freeze the contents of `extra_data` upon model creation recursively
    # TODO validate that all values in `extra_data` are json-serializable
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        """Check if two models represent the same concept."""
        if not isinstance(other, MergedObject):
            return False
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        """The hash of the model is the hash of its uuid."""
        return hash(self.uuid)


class BotResponses:
    """
    A class that represents a stream of responses from a bot. It is an async iterator that yields `MessageEnvelope`
    objects. It also has a method `get_all_responses` that will block until all the responses are received and then
    return them as a list.
    """

    _END_OF_RESPONSES = object()

    def __init__(self) -> None:
        self.responses_so_far: "List[MessageEnvelope]" = []
        self._response_queue: "Optional[Queue[Union[MessageEnvelope, object, Exception]]]" = Queue()
        self._error: Optional[ErrorWrapper] = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._error:
            raise self._error

        if self._response_queue is None:
            raise StopAsyncIteration

        response = await self._response_queue.get()

        if isinstance(response, Exception):
            self._error = ErrorWrapper(error=response)
            raise self._error

        if response is self._END_OF_RESPONSES:
            self._response_queue = None
            raise StopAsyncIteration

        self.responses_so_far.append(response)
        return response

    async def get_all_responses(self) -> "List[MessageEnvelope]":
        """Wait until all the responses are received and return them as a list."""
        # make sure all responses are fetched
        async for _ in self:
            pass
        return self.responses_so_far

    async def get_final_response(self) -> "Optional[MessageEnvelope]":
        """Wait until all the responses are received and return the last one or None if there are no responses."""
        responses = await self.get_all_responses()
        return responses[-1] if responses else None


# noinspection PyProtectedMember
class SingleTurnContext:
    # pylint: disable=import-outside-toplevel,protected-access,too-many-arguments
    """
    A context object that is passed to a single turn handler function. It is meant to be used as a facade for the
    `MergedBot` and `MergedMessage` objects. It also has a method `yield_response` that is meant to be used by the
    single turn handler function to yield a response to the request.
    """

    def __init__(
        self,
        merger: BotMerger,
        this_bot: "MergedBot",
        channel: "MergedChannel",
        request: "MergedMessage",
        bot_responses: BotResponses,
    ) -> None:
        self.merger = merger
        self.this_bot = this_bot
        self.channel = channel
        self.request = request
        self._bot_responses = bot_responses

    async def trigger_another_bot(self, another_bot: Union["MergedBot", str], request: MessageType) -> BotResponses:
        """Trigger another bot with a request and return a stream of responses from that bot."""
        from botmerger.models import MergedMessage, MessageEnvelope

        if isinstance(another_bot, str):
            another_bot = await self.merger.find_bot(another_bot)

        if isinstance(request, MessageEnvelope):
            return another_bot.trigger(request.message)
        if isinstance(request, MergedMessage):
            return another_bot.trigger(request)

        # this is neither `MessageEnvelope` nor `MergedMessage` so we assume it is `MessageContent`
        request = await self.channel.new_message(self.this_bot, request)
        return another_bot.trigger(request)

    async def get_another_bot_final_response(
        self, another_bot: Union["MergedBot", str], request: MessageType
    ) -> "Optional[MessageEnvelope]":
        """Get the final response from another bot."""
        responses = await self.trigger_another_bot(another_bot, request)
        return await responses.get_final_response()

    async def yield_response(
        self, response: MessageType, show_typing_indicator: Optional[bool] = None, **kwargs
    ) -> None:
        """
        Yield a response to the request. If `show_typing_indicator` is specified it will override the value of
        `show_typing_indicator` in the response that was passed in.
        """
        from botmerger.models import MergedMessage, MessageEnvelope

        # TODO are we sure all these conditions make sense ? what is our philosophy when it comes to relations between
        #  channels and messages as well as between messages themselves ?
        #  HERE IS WHAT NEEDS TO BE CORRECTED:
        #    - if `response` belong to a different channel than a cloned version of `response` should be created with
        #      `channel` set to `self.request.channel`
        #    - but what if we start to maintain some sort of message history and `response` belongs to the same channel
        #      as `self.request` but its position in the history is wrong ? should we clone it then ?
        if isinstance(response, MessageEnvelope):
            if show_typing_indicator is not None and response.show_typing_indicator != show_typing_indicator:
                # we need to create a new MessageEnvelope object with a different value of `show_typing_indicator`
                response = copy(response)
                response.show_typing_indicator = show_typing_indicator
        else:
            if not isinstance(response, MergedMessage):
                # `response` is plain message content
                response = await self.merger.create_message(
                    channel=self.channel,
                    sender=self.this_bot,
                    content=response,
                    **kwargs,
                )
            response = MessageEnvelope(response, show_typing_indicator=show_typing_indicator or False)

        self._bot_responses._response_queue.put_nowait(response)

    async def yield_from(
        self, another_bot_responses: BotResponses, show_typing_indicator: Optional[bool] = None
    ) -> None:
        """Yield all the responses from another bot."""
        async for response in another_bot_responses:
            await self.yield_response(response, show_typing_indicator=show_typing_indicator)
