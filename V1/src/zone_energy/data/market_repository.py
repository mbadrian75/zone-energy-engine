from datetime import datetime
from typing import Iterator

from pymongo import ASCENDING, MongoClient

from zone_energy.models import Candle


class MarketDataRepository:
    """
    Read-only access to historical XAUUSD market data stored in MongoDB.
    """

    COLLECTIONS = {
        "D1": "xauusd_d1",
        "H4": "xauusd_h4",
        "H1": "xauusd_h1",
        "M30": "xauusd_m30",
        "M15": "xauusd_m15",
        "M5": "xauusd_m5",
        "M1": "xauusd_m1",
    }

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017/",
        database_name: str = "market_data",
    ) -> None:
        self._client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
        )

        self._db = self._client[database_name]

    def ping(self) -> bool:
        self._client.admin.command("ping")
        return True

    def close(self) -> None:
        self._client.close()

    def _get_collection(self, timeframe: str):
        timeframe = timeframe.upper()

        if timeframe not in self.COLLECTIONS:
            valid = ", ".join(self.COLLECTIONS)

            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Valid timeframes: {valid}"
            )

        return self._db[self.COLLECTIONS[timeframe]]

    @staticmethod
    def _document_to_candle(document: dict) -> Candle:
        return Candle(
            datetime=document["datetime"],
            open=float(document["open"]),
            high=float(document["high"]),
            low=float(document["low"]),
            close=float(document["close"]),
            volume=float(document.get("volume", 0.0)),
        )

    def get_candles(
        self,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:

        if start >= end:
            raise ValueError("start must be earlier than end")

        collection = self._get_collection(timeframe)

        query = {
            "datetime": {
                "$gte": start,
                "$lt": end,
            }
        }

        cursor = (
            collection
            .find(query)
            .sort("datetime", ASCENDING)
        )

        return [
            self._document_to_candle(document)
            for document in cursor
        ]

    def stream_candles(
        self,
        timeframe: str,
        start: datetime,
        end: datetime,
        batch_size: int = 10_000,
    ) -> Iterator[Candle]:

        if start >= end:
            raise ValueError("start must be earlier than end")

        collection = self._get_collection(timeframe)

        query = {
            "datetime": {
                "$gte": start,
                "$lt": end,
            }
        }

        cursor = (
            collection
            .find(query)
            .sort("datetime", ASCENDING)
            .batch_size(batch_size)
        )

        for document in cursor:
            yield self._document_to_candle(document)