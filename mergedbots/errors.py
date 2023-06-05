"""This module contains all MergedBots errors."""
import traceback


class MergedBotsError(Exception):
    """Base class for all MergedBots errors."""


class BotHandleTakenError(MergedBotsError):
    """Raised when a bot with the same handle already exists."""


class BotNotFoundError(MergedBotsError):
    """Raised when a bot with the given handle does not exist."""


class ErrorWrapper(MergedBotsError):
    """This wrapper is used to contain errors that occurred outside main coroutine."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        # TODO is there a better way to automatically display the full traceback of the nested error except
        #  preformatting the whole thing into the wrapper error message ?
        super().__init__(
            "\n\nSEE NESTED EXCEPTION BELOW\n\n"
            + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        )
        # super().__init__(f"{type(error).__module__}.{type(error).__name__}: {error}")
