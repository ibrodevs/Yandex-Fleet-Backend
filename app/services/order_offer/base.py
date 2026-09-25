from __future__ import annotations

from abc import ABC, abstractmethod


class OrderOfferProvider(ABC):
    @abstractmethod
    async def get_active_offers(self, driver_id: str):
        raise NotImplementedError

    @abstractmethod
    async def accept_offer(self, offer_id: str):
        raise NotImplementedError

    @abstractmethod
    async def reject_offer(self, offer_id: str):
        raise NotImplementedError


class UnsupportedYandexOfferProvider(OrderOfferProvider):
    async def get_active_offers(self, driver_id: str):
        return []

    async def accept_offer(self, offer_id: str):
        raise RuntimeError("Public Yandex Fleet API does not expose this operation.")

    async def reject_offer(self, offer_id: str):
        raise RuntimeError("Public Yandex Fleet API does not expose this operation.")
