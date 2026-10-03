from zone_energy.replay.replay_engine import ReplayEngine


class ReplayRunner:
    """Stream real market candles and save periodic and final checkpoints."""

    def __init__(self, market, results, boundary_service, config, year_candles):
        self.market = market
        self.results = results
        self.engine = ReplayEngine(config, year_candles, boundary_service)

    def run(self, *, start, end, run_id, symbol="XAUUSD", checkpoint_every=100):
        if start >= end:
            raise ValueError("Replay start must precede end")
        if symbol != "XAUUSD":
            raise ValueError("Current candle repository supports XAUUSD only")
        if not isinstance(checkpoint_every, int) or isinstance(checkpoint_every, bool) or checkpoint_every <= 0:
            raise ValueError("checkpoint_every must be a positive integer")
        if self.engine.current_index != -1:
            raise ValueError("Use a fresh replay runner for each complete run")
        last_checkpoint = None
        last_saved_index = -1
        last_candle = None

        def save(state, index, candle):
            nonlocal last_checkpoint, last_saved_index
            last_checkpoint = self.results.save_checkpoint(
                state.zones, run_id=run_id, symbol=symbol, current_candle_index=index,
                year_candles=self.engine.year_candles, config=self.engine.config,
                replay_context={"start": start, "end": end, "candle_datetime": candle.datetime,
                                "unattributed_breaks": state.unattributed_breaks,
                                "invalidated_reactions": state.invalidated_reactions,
                                "next_zone_id": state.next_zone_id,
                                "next_interaction_id": state.next_interaction_id},
            )
            last_saved_index = index

        def checkpoint(state, index, candle):
            if (index + 1) % checkpoint_every == 0:
                save(state, index, candle)

        for candle in self.market.stream_candles(self.engine.config.timeframe.value, start, end):
            self.engine.process(candle, before_commit=checkpoint)
            last_candle = candle
        if last_candle is None:
            raise ValueError("No market candles found in the requested range")
        if last_saved_index != self.engine.current_index:
            save(self.engine.state, self.engine.current_index, last_candle)
        return {"candles": self.engine.current_index + 1,
                "zones": len(self.engine.state.zones),
                "unattributed_breaks": len(self.engine.state.unattributed_breaks),
                "invalidated_reactions": len(self.engine.state.invalidated_reactions),
                "last_checkpoint": last_checkpoint}
