from abc import ABC, abstractmethod


class NotificationTransport(ABC):

    @abstractmethod
    def send_message(self, content: str) -> bool:

        raise NotImplementedError

    @abstractmethod
    def send_embed(self, embed: dict) -> bool:

        raise NotImplementedError
