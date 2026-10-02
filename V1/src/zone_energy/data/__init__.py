"""Data repositories; import the database driver only when a client is needed."""

__all__ = ["MarketDataRepository", "EngineResultsRepository"]


def __getattr__(name):
    if name == "MarketDataRepository":
        from .market_repository import MarketDataRepository
        return MarketDataRepository
    if name == "EngineResultsRepository":
        from .engine_results_repository import EngineResultsRepository
        return EngineResultsRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
