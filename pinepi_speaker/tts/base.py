"""Abstract TTS adapter interface."""

from abc import ABC, abstractmethod


class TTSAdapter(ABC):
    """Base class for all TTS backends.

    Subclasses must implement :meth:`speak`. The method is expected to be
    non-blocking (enqueue internally) or blocking — callers don't assume either.
    """

    @abstractmethod
    def speak(self, text: str) -> None:
        """Synthesise and play *text*."""
        ...

    def shutdown(self) -> None:
        """Optional cleanup called on daemon exit."""
        pass
