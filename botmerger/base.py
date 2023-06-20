# pylint: disable=no-name-in-module,too-many-arguments
"""Base classes for the BotMerger library."""
from abc import ABC, abstractmethod
from asyncio import Queue
from typing import Any, TYPE_CHECKING, Optional, Dict, Callable, Awaitable, Union, List, Tuple
from uuid import uuid4

from pydantic import BaseModel, UUID4, Field

from botmerger.errors import ErrorWrapper

if TYPE_CHECKING:
    from botmerger.models import MergedBot, MergedChannel, MergedMessage, MergedParticipant

SingleTurnHandler = Callable[["SingleTurnContext"], Awaitable[None]]
MessageContent = Union[str, BaseModel, Any]  # a string, a Pydantic model, a dataclass or a json-serializable object
MessageType = Union["MergedMessage", MessageContent]
ObjectKey = Union[UUID4, Tuple[Any, ...]]


class BotMerger(ABC):
    """
    An abstract factory of everything else in this library and also the low level implementation of everything else
    in this library. Almost all the methods of almost all the other classes in this library are just a facade for
    methods of this class.
    """

    @abstractmethod
    async def trigger_bot(self, bot: "MergedBot", request: "MergedMessage") -> "BotResponses":
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
        self,
        thread_uuid: UUID4,
        channel: "MergedChannel",
        sender: "MergedParticipant",
        content: "MessageType",
        indicate_typing_afterwards: Optional[bool],
        responds_to: Optional["MergedMessage"],
        goes_after: Optional["MergedMessage"],
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a message in a given channel. If `content` is another `MergedMessage` instance, then
        `ForwardedMessage` will be created instead of `OriginalMessage`.
        """

    @abstractmethod
    async def create_next_message(
        self,
        thread_uuid: UUID4,
        channel: "MergedChannel",
        sender: "MergedParticipant",
        content: "MessageType",
        indicate_typing_afterwards: Optional[bool],
        responds_to: Optional["MergedMessage"],
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a message in a given channel that goes after the last message in a given thread. If `content` is
        another `MergedMessage` instance, then `ForwardedMessage` will be created instead of `OriginalMessage`.
        """

    @abstractmethod
    async def find_message(self, uuid: UUID4) -> "MergedMessage":
        """Find a message by its uuid."""

    @abstractmethod
    async def set_mutable_state(self, key: ObjectKey, state: Any) -> None:
        """Set a mutable state associated with a given key."""

    @abstractmethod
    async def get_mutable_state(self, key: ObjectKey) -> Optional[Any]:
        """Get a mutable state associated with a given key."""


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
    # TODO replace uuid with something that also includes the id of the BotMerger instance this object belongs to
    uuid: UUID4 = Field(default_factory=uuid4)
    # TODO freeze the contents of `extra_data` upon model creation recursively
    # TODO validate that all values in `extra_fields` are json-serializable
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
    A class that represents a stream of responses from a bot. It is an async iterator that yields `MergedMessage`
    objects. It also has a method `get_all_responses` that will block until all the responses are received and then
    return them as a list.
    """

    _END_OF_RESPONSES = object()

    def __init__(self, request: "MergedMessage") -> None:
        self.request = request
        self.responses_so_far: List["MergedMessage"] = []
        self._response_queue: Optional[Queue[Union["MergedMessage", object, Exception]]] = Queue()
        self._error: Optional[ErrorWrapper] = None

    def __aiter__(self) -> "BotResponses":
        return self

    async def __anext__(self) -> "MergedMessage":
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

    async def get_all_responses(self) -> List["MergedMessage"]:
        """Wait until all the responses are received and return them as a list."""
        # make sure all responses are fetched
        async for _ in self:
            pass
        return self.responses_so_far

    async def get_final_response(self) -> Optional["MergedMessage"]:
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

    async def yield_response(
        self, response: MessageType, indicate_typing_afterwards: Optional[bool] = None, **kwargs
    ) -> "MergedMessage":
        response = await self.merger.create_next_message(
            thread_uuid=self.request.thread_uuid,
            channel=self.channel,
            sender=self.this_bot,
            content=response,
            indicate_typing_afterwards=indicate_typing_afterwards,
            responds_to=self.request,
            **kwargs,
        )
        self._bot_responses._response_queue.put_nowait(response)
        return response

    async def yield_interim_response(self, response: MessageType, **kwargs) -> "MergedMessage":
        return await self.yield_response(response, indicate_typing_afterwards=True, **kwargs)

    async def yield_final_response(self, response: MessageType, **kwargs) -> "MergedMessage":
        return await self.yield_response(response, indicate_typing_afterwards=False, **kwargs)

    async def yield_from(
        self, another_bot_responses: BotResponses, indicate_typing_afterwards: Optional[bool] = None
    ) -> None:
        async for response in another_bot_responses:
            await self.yield_response(response, indicate_typing_afterwards=indicate_typing_afterwards)
