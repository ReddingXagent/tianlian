"""PushProvider 接口定义."""

from abc import ABC, abstractmethod


class PushProvider(ABC):
    @abstractmethod
    def send(self, end_user_id: int, title: str, body: str, payload: dict) -> bool:
        """发送一条 App push; best-effort 语义由实现保证."""
