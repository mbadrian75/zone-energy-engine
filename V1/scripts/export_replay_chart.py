"""Export real MongoDB candles around an interaction to a standalone HTML chart."""
import argparse
from html import escape
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.models import ZoneType


def render_chart(candles, zones, origin, move, break_index, first, last):
    """Display raw patterns separately from reactions actually stored by replay."""
    if not (0 <= first <= move.start_index <= break_index <= last < len(candles)):
        raise ValueError("Chart window must contain the interaction start and break")
    width, height, left, top = 1500, 740, 85, 60
    plot_width, plot_height = 1370, 570
    visible = candles[first:last + 1]
    low = min([bar.low for bar in visible] + [origin.lower_price])
    high = max([bar.high for bar in visible] + [origin.upper_price])
    padding = (high - low) * .1 or 1
    low, high = low - padding, high + padding
    step = plot_width / len(visible)
    x = lambda index: left + (index - first + .5) * step
    y = lambda price: top + (high - price) / (high - low) * plot_height
    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             'role="img" aria-label="Actual replay candlestick chart">',
             '<rect width="100%" height="100%" fill="white"/>']
    def label(px, py, value, color="#334155", size=13):
        parts.append(f'<text x="{px:.2f}" y="{py:.2f}" fill="{color}" '
                     f'font-size="{size}">{escape(str(value))}</text>')
    for tick in range(9):
        price = low + (high - low) * tick / 8
        py = y(price)
        parts.append(f'<line x1="{left}" y1="{py}" x2="{left + plot_width}" y2="{py}" stroke="#e2e8f0"/>')
        label(5, py + 4, f"{price:.3f}")
    parts.append(f'<rect x="{left}" y="{y(origin.upper_price)}" width="{plot_width}" '
                 f'height="{y(origin.lower_price)-y(origin.upper_price)}" fill="#ef4444" fill-opacity=".10" '
                 'stroke="#ef4444" stroke-dasharray="6 4"/>')
    label(left + 8, y(origin.upper_price) - 8,
          f"Origin zone {origin.id}: {origin.lower_price:.3f}–{origin.upper_price:.3f}", "#b91c1c")
    accepted = {}
    for zone in zones:
        for interaction in zone.interactions:
            accepted.setdefault(interaction.start_index, []).append((zone.id, interaction.id))
    rows = []
    for index in range(first, last + 1):
        bar = candles[index]
        px = x(index)
        color = "#059669" if bar.close >= bar.open else "#dc2626"
        parts.append(f'<g><title>{escape(bar.datetime.isoformat())} | index={index} | '
                     f'O={bar.open} H={bar.high} L={bar.low} C={bar.close}</title>')
        parts.append(f'<line x1="{px}" y1="{y(bar.high)}" x2="{px}" y2="{y(bar.low)}" stroke="{color}"/>')
        parts.append(f'<rect x="{px-step*.28}" y="{min(y(bar.open),y(bar.close))}" '
                     f'width="{step*.56}" height="{max(abs(y(bar.open)-y(bar.close)),1)}" fill="{color}"/></g>')
        if (index - first) % max(1, len(visible) // 12) == 0:
            label(px - 10, top + plot_height + 22, index)
            label(px - 35, top + plot_height + 42, bar.datetime.strftime("%m-%d %H:%M"), size=10)
        pattern = ""
        if 0 < index < len(candles) - 1:
            previous, following = candles[index - 1], candles[index + 1]
            earlier = [interaction for zone in zones for interaction in zone.interactions
                       if interaction.start_index < index]
            previous_type = None
            if earlier:
                latest = max(earlier, key=lambda interaction: interaction.start_index)
                origin_bar = candles[latest.start_index]
                if latest.start_price == origin_bar.high:
                    previous_type = ZoneType.RESISTANCE
                elif latest.start_price == origin_bar.low:
                    previous_type = ZoneType.SUPPORT
            reversal = ReversalDetector.detect(
                previous, bar, following, index-1, index, index+1,
                previous_type=previous_type,
            )
            both = bar.high > previous.high and bar.high > following.high and bar.low < previous.low and bar.low < following.low
            if reversal:
                pattern = f"{reversal.type.value} (confirmed at {index+1})"
                if both:
                    pattern += " — dual extreme: opposite previous stored reaction"
                py = y(reversal.extreme_price)
                marker_color = "#2563eb" if reversal.type.value == "support" else "#9333ea"
                parts.append(f'<circle cx="{px}" cy="{py}" r="5" fill="{marker_color}"><title>{escape(pattern)}</title></circle>')
                label(px + 5, py - 8, "S" if reversal.type.value == "support" else "R", marker_color, 11)
            elif both:
                pattern = f"Ambiguous high AND low: no previous reaction at {index+1}"
                label(px - 4, y(bar.low) + 18, "×", "#d97706", 20)
        stored = "; ".join(f"zone {z}, interaction {i}" for z, i in accepted.get(index, []))
        if stored:
            parts.append(f'<rect x="{px-7}" y="{y(bar.low)+23}" width="14" height="14" fill="#0f172a"><title>{escape(stored)}</title></rect>')
        rows.append(f'<tr><td>{index}</td><td>{escape(bar.datetime.isoformat())}</td>'
                    f'<td>{bar.open}</td><td>{bar.high}</td><td>{bar.low}</td><td>{bar.close}</td>'
                    f'<td>{escape(pattern)}</td><td>{escape(stored)}</td></tr>')
    for index, text, color in ((move.start_index, f"Interaction {move.id} starts", "#0f172a"),
                                (break_index, f"Origin breaks: {break_index}", "#b91c1c")):
        px = x(index)
        parts.append(f'<line x1="{px}" y1="{top}" x2="{px}" y2="{top+plot_height}" stroke="{color}" stroke-dasharray="4 4"/>')
        label(max(left, min(px - 70, width - 230)), 25 if index == move.start_index else 45, text, color)
    parts.append('</svg>')
    return ('<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
            '<title>بررسی مسیر واقعی قیمت</title><style>body{font-family:Tahoma,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}'
            'svg{width:100%;min-width:1000px} .chart{overflow:auto;background:white}table{border-collapse:collapse;width:100%;font-size:12px}'
            'td,th{border:1px solid #cbd5e1;padding:6px}tr:nth-child(even){background:white}</style>'
            '<h2>کندل‌های واقعی بین واکنش و شکست زون مبدأ</h2>'
            '<p>دایره آبی S: کف سه کندلی؛ دایره بنفش R: سقف سه کندلی. تأیید در کندل بعد انجام می‌شود. '
            'در کندل هم‌زمان سقف و کف، نوع مخالف واکنش قبلی انتخاب می‌شود. '
            'علامت نارنجی ×: برای انتخاب نوع، واکنش قبلی در دسترس نیست. '
            'مربع سیاه: شروع Interaction ثبت‌شده در Replay.</p>'
            '<p>الگوها با قاعده فعلی و واکنش قبلی موجود در checkpoint محاسبه می‌شوند؛ '
            'مربع‌های سیاه، تاریخچه ثبت‌شده همان اجرا هستند. وجود الگوی سه کندلی به‌تنهایی به معنی واکنش پذیرفته‌شده به زون نیست. '
            'تنها محدوده زون مبدأ نمایش داده شده؛ برای دانستن تماس با زون‌های دیگر باید آن‌ها را جداگانه بررسی کرد. '
            'برای دیدن اطلاعات کندل، نشانگر را روی آن نگه دارید.</p>'
            '<div class="chart" dir="ltr">' + ''.join(parts) + '</div>'
            '<h3>جزئیات کندل‌ها و الگوهای تشخیص‌داده‌شده</h3><div style="overflow:auto" dir="ltr"><table>'
            '<tr><th>Index</th><th>Time</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Three-candle pattern</th><th>Stored reaction</th></tr>'
            + ''.join(rows) + '</table></div></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint-index", type=int, default=503)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--interaction-id", type=int, default=45)
    parser.add_argument("--break-index", type=int, default=127)
    parser.add_argument("--padding", type=int, default=8)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--output", default="replay-zone19-chart.html")
    args = parser.parse_args()
    if args.padding < 0:
        parser.error("--padding must be nonnegative")
    from zone_energy.data import EngineResultsRepository, MarketDataRepository
    uri = os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/")
    market = MarketDataRepository(uri, args.database)
    results = EngineResultsRepository(uri, args.database)
    try:
        identifier = json.dumps([args.run_id, "XAUUSD", args.timeframe, args.checkpoint_index], separators=(",", ":"))
        document = results.get_checkpoint(identifier)
        if document is None:
            raise ValueError("Checkpoint not found")
        zones = results.load_zones(identifier)
        matches = [(zone, move) for zone in zones for move in zone.interactions if move.id == args.interaction_id]
        if len(matches) != 1:
            raise ValueError("Interaction not uniquely found")
        origin, move = matches[0]
        context = document["replay_context"]
        bars = market.get_candles(args.timeframe, context["start"], context["end"])
        if len(bars) <= args.checkpoint_index or bars[args.checkpoint_index].datetime != context["candle_datetime"]:
            raise ValueError("Candle indexing no longer matches checkpoint")
        events = [event for event in context["unattributed_breaks"]
                  if event["zone_id"] == origin.id and event["candle_index"] == args.break_index]
        if len(events) != 1 or bars[args.break_index].close != events[0]["close"]:
            raise ValueError("Origin break does not match the selected checkpoint/candles")
        first = max(0, move.start_index - args.padding)
        last = min(args.checkpoint_index, args.break_index + args.padding)
        html = render_chart(bars, zones, origin, move, args.break_index, first, last)
        output = Path(args.output).resolve()
        output.write_text(html, encoding="utf-8")
        print(f"Zone: {origin.id}; interaction: {move.id}; start: {move.start_index}; break: {args.break_index}")
        print(f"Chart candles: {first}–{last}")
        print(f"Chart: {output}")
    finally:
        results.close()
        market.close()


if __name__ == "__main__":
    main()
