"""This module contains all MergedBots errors."""


class MergedBotsError(Exception):
    """Base class for all MergedBots errors."""


class BotHandleTakenError(MergedBotsError):
    """Raised when a bot with the same handle already exists."""


class BotNotFoundError(MergedBotsError):
    """Raised when a bot with the given handle does not exist."""


class WrongMergedObjectError(MergedBotsError):
    """Raised when an object is not of the expected type."""


class ErrorWrapper(MergedBotsError):
    """This wrapper is used to contain errors that occurred outside main coroutine."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        super().__init__(f"{type(error).__module__}.{type(error).__name__}: {error}")
