# pylint: disable=protected-access,no-name-in-module,unused-argument
"""
A bot, whose fulfillment_func is called once per the whole user interaction. NonEventBasedChatSession is used
send and receive messages in an algorithmic way, without events.
"""
import asyncio
import logging
from typing import Awaitable, Callable, AsyncGenerator

from pydantic import PrivateAttr, BaseModel

from mergedbots.base import MergedParticipant
from mergedbots.errors import ErrorWrapper
from mergedbots.models import MergedBot, MergedMessage

SequentialFulfillmentFunc = Callable[[MergedBot, "ConversationSequence"], Awaitable[None]]

logger = logging.getLogger(__name__)

_INBOUND_MSG_SENTINEL = object()
_SESSION_ENDED_SENTINEL = object()


class SequentialMergedBotWrapper(BaseModel):
    """
    A bot, whose fulfillment_func is called once per the whole user interaction. NonEventBasedChatSession is used to
    send and receive messages in a sequential way, without events.
    """

    bot: MergedBot

    _fulfillment_func: SequentialFulfillmentFunc = PrivateAttr(default=None)
    # TODO introduce an alternative implementation that uses Redis for queues
    _sessions: PrivateAttr(dict[MergedParticipant, "ConversationSequence"]) = PrivateAttr(default_factory=dict)

    def __init__(self, bot: MergedBot, **kwargs) -> None:
        super().__init__(bot=bot, **kwargs)
        self.bot(self._fulfill_single_msg)

    async def _fulfill_single_msg(self, bot: MergedBot, message: MergedMessage) -> AsyncGenerator[MergedMessage, None]:
        """Fulfill a message."""
        session = self._sessions.get(message.originator)
        is_new_session = False

        if not session:
            session = ConversationSequence()
            self._sessions[message.originator] = session
            is_new_session = True

        await session._inbound_queue.put(message)

        if is_new_session:
            asyncio.create_task(self._run_session_till_the_end(session))

        while True:
            response = await session._outbound_queue.get()

            if response is _INBOUND_MSG_SENTINEL:
                # new incoming message is now being awaited for - exit current `fulfill` and let it be processed
                # by a new call to `fulfill`
                return
            if response is _SESSION_ENDED_SENTINEL:
                # the session has finished running - make room for a new session from the same originator in the future
                self._sessions.pop(session.originator)
                return
            if isinstance(response, Exception):
                raise ErrorWrapper(error=response)

            yield response

    async def _run_session_till_the_end(self, session: "ConversationSequence") -> None:
        try:
            await self._fulfillment_func(self.bot, session)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # don't lose the exception
            await session._outbound_queue.put(exc)
        await session._outbound_queue.put(_SESSION_ENDED_SENTINEL)

    def __call__(self, fulfillment_func: SequentialFulfillmentFunc) -> SequentialFulfillmentFunc:
        self._fulfillment_func = fulfillment_func
        try:
            fulfillment_func.merged_bot = self.bot
        except AttributeError:
            # the trick with setting `merged_bot` attribute on a function does not work with methods, but that's fine
            logger.debug("could not set `merged_bot` attribute on %r", fulfillment_func)
        return fulfillment_func


class ConversationSequence(BaseModel):
    """
    An object that represents a chat session between a bot and a user (or, more generally, a bot and an originator,
    because this might also be two bots interacting with each other).
    """

    _inbound_queue: asyncio.Queue[MergedMessage] = PrivateAttr(default_factory=asyncio.Queue)
    _outbound_queue: asyncio.Queue[MergedMessage | object] = PrivateAttr(default_factory=asyncio.Queue)
    _first_message: bool = PrivateAttr(default=True)

    async def wait_for_incoming(self) -> MergedMessage:
        """Wait for the next message from the originator."""
        if self._first_message:
            self._first_message = False
        else:
            # for the rest of the messages we need to notify `_fulfill_single_msg` that it's time to "restart"
            # the event
            await self._outbound_queue.put(_INBOUND_MSG_SENTINEL)
        message = await self._inbound_queue.get()
        return message

    async def yield_outgoing(self, message: MergedMessage) -> None:
        """Send a message to the originator."""
        # TODO think how to make sure that the library users will spawn their outbound messages from the latest
        #  inbound message and not a more ancient one
        await self._outbound_queue.put(message)
