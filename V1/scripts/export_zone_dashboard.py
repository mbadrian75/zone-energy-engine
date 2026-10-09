"""Export a read-only, offline zone dashboard from a saved replay checkpoint."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
from zone_energy.models import InteractionState


def dashboard_data(zones, candles, config, index, year_candles, run_id):
    if not candles or candles[-1]["index"] != index:
        raise ValueError("Chart must end at the checkpoint candle")
    effective = EffectiveZoneEnergyCalculator(config)
    decay = InteractionTimeDecayCalculator(config)
    rows, opened = [], []
    for zone in zones:
        energy = effective.calculate(zone, index, year_candles)
        moves = []
        for move in zone.interactions:
            row = asdict(move)
            row["state"] = move.state.value
            if move.state == InteractionState.CLOSED:
                age, weight, contribution = decay.evaluate(move, index, year_candles)
                row.update(age=age, weight=weight, contribution=contribution)
            else:
                row.update(age=index-move.start_index, weight=None, contribution=None)
                opened.append({"zone_id":zone.id, "interaction_id":move.id,
                               "start_index":move.start_index,"start_price":move.start_price})
            moves.append(row)
        rows.append({"id":zone.id,"type":zone.type.value,"state":zone.state.value,
                     "lower":zone.lower_price,"upper":zone.upper_price,
                     "creation_index":zone.creation_index,"creation_extreme":zone.creation_extreme,
                     "energy":energy,"interactions":moves})
    if len(opened) > 1:
        raise ValueError("Checkpoint contains multiple OPEN interactions")
    return {"run_id":run_id,"index":index,"timeframe":config.timeframe.value,
            "year_candles":year_candles,"remaining_weight":config.yearly_remaining_weight,
            "last_candle":candles[-1],"candles":candles,"zones":rows,"open_move":opened[0] if opened else None}


def render_dashboard(data):
    # Escaping '<' prevents checkpoint text from closing the JSON script element.
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", payload)


TEMPLATE = '''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>گزارش زون‌ها</title>
<style>body{font:15px Tahoma,Arial;background:#f1f5f9;color:#0f172a;margin:24px}h1{font-size:23px}
.box{background:white;padding:18px;border-radius:12px;margin:16px 0}p{line-height:1.8}
input,select,button{font:inherit;padding:8px;margin:4px;border:1px solid #94a3b8;border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #e2e8f0;text-align:right}
tbody tr{cursor:pointer}tbody tr:hover{background:#eff6ff}.scroll{overflow:auto;max-height:440px}
svg{width:100%;min-width:900px}#chart{overflow:auto} .muted{color:#475569}#detail{scroll-margin-top:20px}</style>
<h1>گزارش زون‌ها و انرژی واکنش‌ها</h1><div class="box" id="summary"></div>
<p class="muted">وضعیت، نقش و انرژی زون‌ها مربوط به آخرین کندل checkpoint است؛ رنگ زون وضعیت تاریخی آن در همهٔ کندل‌ها را نشان نمی‌دهد.
زون‌های هم‌پوشان با محدودهٔ قیمت چارت نمایش داده می‌شوند. با انتخاب هر زون، مرزهای آن و سهم واکنش‌هایش را ببینید.</p>
<div class="box"><label>وضعیت <select id="state"><option value="active">فعال</option><option value="all">همه</option><option value="broken">شکسته</option></select></label>
<label>نقش <select id="role"><option value="all">همه</option><option value="support">حمایت</option><option value="resistance">مقاومت</option></select></label>
<label>شناسه زون <input id="search" type="number" min="1" placeholder="همه"></label><button id="clear">لغو انتخاب زون</button>
<p id="count"></p><div id="chart"></div></div>
<div class="box scroll"><table><thead><tr><th>زون</th><th>نقش فعلی</th><th>وضعیت</th><th>مرز پایین</th><th>مرز بالا</th><th>انرژی فعلی</th><th>تعداد واکنش‌ها</th></tr></thead><tbody id="zones"></tbody></table></div>
<div class="box" id="detail">برای دیدن سهم واکنش‌ها، یک زون را انتخاب کنید.</div>
<script id="data" type="application/json">__DATA__</script><script>
const d=JSON.parse(document.getElementById('data').textContent);let selected=null;
const el=id=>document.getElementById(id),fmt=(x,n=3)=>x===null||x===undefined?'نامشخص':Number(x).toFixed(n);
const kind=x=>x==='support'?'حمایت':'مقاومت',status=x=>x==='active'?'فعال':'شکسته';
function cell(tr,value){const td=document.createElement('td');td.textContent=value;tr.append(td)}
const summary=el('summary');
for(const line of [`Run: ${d.run_id}`,`آخرین کندل: ${d.index} | ${d.last_candle.datetime} | ${d.timeframe} | Close: ${fmt(d.last_candle.close)}`,
`زون‌های فعال: ${d.zones.filter(z=>z.state==='active').length} | شکسته: ${d.zones.filter(z=>z.state==='broken').length}`,
d.open_move?`حرکت باز: ${d.open_move.interaction_id} | زون مبدأ: ${d.open_move.zone_id} | کندل مبدأ: ${d.open_move.start_index} | قیمت: ${fmt(d.open_move.start_price)} | انرژی هنوز نهایی نشده`:'حرکت باز وجود ندارد',
`کاهش زمانی مستقل: وزن سالانه ${d.remaining_weight} در ${d.year_candles} کندل`]){const p=document.createElement('p');p.textContent=line;summary.append(p)}
function filtered(){return d.zones.filter(z=>(el('state').value==='all'||z.state===el('state').value)&&(el('role').value==='all'||z.type===el('role').value)&&(!el('search').value||z.id===Number(el('search').value)))}
function detail(z){selected=z.id;el('detail').replaceChildren();const title=document.createElement('h2');title.textContent=`زون ${z.id} — ${kind(z.type)}، ${status(z.state)} — انرژی ${fmt(z.energy)}`;el('detail').append(title);
const p=document.createElement('p');p.textContent=`تشکیل در کندل ${z.creation_index}، قیمت ${fmt(z.creation_extreme)}. سن هر واکنش از کندل شروع خودش محاسبه می‌شود. واکنش باز و انرژی نامشخص در جمع مشارکت ندارند.`;el('detail').append(p);
const wrap=document.createElement('div');wrap.className='scroll';const table=document.createElement('table');const head=document.createElement('tr');
for(const name of ['Interaction','شروع','پایان','وضعیت','انرژی حرکت','انرژی شکست‌ها','انرژی پایه','سن به کندل','وزن باقی‌مانده','سهم فعلی'])cell(head,name);table.append(head);
for(const m of z.interactions){const tr=document.createElement('tr');for(const v of [m.id,m.start_index,m.end_index??'—',m.state==='open'?'باز':'بسته',fmt(m.movement_energy),fmt(m.total_break_evidence),fmt(m.base_energy),m.age,m.weight===null?'—':fmt(m.weight*100,2)+'٪',fmt(m.contribution)])cell(tr,v);table.append(tr)}
wrap.append(table);el('detail').append(wrap);draw();}
function draw(){const bars=d.candles;const candidates=filtered();let low=Math.min(...bars.map(b=>b.low)),high=Math.max(...bars.map(b=>b.high));const chosen=d.zones.find(z=>z.id===selected);
if(chosen){low=Math.min(low,chosen.lower);high=Math.max(high,chosen.upper)}const pad=(high-low)*.08||1;low-=pad;high+=pad;
const shown=candidates.filter(z=>z.upper>=low&&z.lower<=high);if(chosen&&!shown.some(z=>z.id===chosen.id))shown.push(chosen);
el('count').textContent=`${candidates.length} زون در جدول؛ ${shown.length} زون در محدودهٔ چارت. کندل‌ها: ${bars[0].index} تا ${d.index}`;
const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 1450 670');svg.setAttribute('role','img');svg.setAttribute('aria-label','چارت کندل‌های واقعی و مرز زون‌ها');
const step=1300/bars.length,x=i=>90+(i-bars[0].index+.5)*step,y=p=>30+(high-p)/(high-low)*570;
function add(tag,attrs,text){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);return e}
for(let i=0;i<=8;i++){const p=low+(high-low)*i/8;add('line',{x1:90,x2:1390,y1:y(p),y2:y(p),stroke:'#e2e8f0'});add('text',{x:4,y:y(p)+4,'font-size':12},fmt(p))}
for(const z of shown){const color=z.state==='broken'?'#64748b':z.type==='support'?'#2563eb':'#dc2626';const top=Math.min(high,z.upper),bottom=Math.max(low,z.lower);
const rect=add('rect',{x:90,y:y(top),width:1300,height:Math.max(1,y(bottom)-y(top)),fill:color,'fill-opacity':z.id===selected?.14:.035,stroke:color,'stroke-width':z.id===selected?3:1,'stroke-dasharray':z.state==='broken'?'6 4':'none'});rect.style.cursor='pointer';const t=document.createElementNS(ns,'title');t.textContent=`زون ${z.id} | ${kind(z.type)} | ${status(z.state)} | ${fmt(z.lower)}–${fmt(z.upper)} | انرژی ${fmt(z.energy)}`;rect.append(t);rect.onclick=()=>detail(z);
if(z.id===selected)add('text',{x:95,y:Math.max(16,y(top)-6),fill:color,'font-size':14},`Zone ${z.id}: ${fmt(z.lower)}–${fmt(z.upper)}`)}
for(const b of bars){const color=b.close>=b.open?'#059669':'#dc2626';add('line',{x1:x(b.index),x2:x(b.index),y1:y(b.high),y2:y(b.low),stroke:color});const body=add('rect',{x:x(b.index)-step*.28,y:Math.min(y(b.open),y(b.close)),width:step*.56,height:Math.max(1,Math.abs(y(b.open)-y(b.close))),fill:color});const t=document.createElementNS(ns,'title');t.textContent=`${b.index} | ${b.datetime} | O=${b.open} H=${b.high} L=${b.low} C=${b.close}`;body.append(t);
if((b.index-bars[0].index)%Math.max(1,Math.floor(bars.length/10))===0)add('text',{x:x(b.index)-12,y:625,'font-size':12},b.index)}
if(chosen)for(const m of chosen.interactions){if(m.start_index>=bars[0].index&&m.start_index<=d.index){add('circle',{cx:x(m.start_index),cy:y(m.start_price),r:5,fill:'#0f172a'});add('text',{x:x(m.start_index)+7,y:y(m.start_price)-7,'font-size':11},m.id)}}
el('chart').replaceChildren(svg);}
function refresh(){el('zones').replaceChildren();for(const z of filtered().sort((a,b)=>(b.energy??-1)-(a.energy??-1))){const tr=document.createElement('tr');for(const v of [z.id,kind(z.type),status(z.state),fmt(z.lower),fmt(z.upper),fmt(z.energy),z.interactions.length])cell(tr,v);tr.onclick=()=>detail(z);el('zones').append(tr)}draw()}
for(const id of ['state','role','search'])el(id).oninput=refresh;el('clear').onclick=()=>{selected=null;el('detail').textContent='برای دیدن سهم واکنش‌ها، یک زون را انتخاب کنید.';draw()};refresh();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--candles", type=int, default=120)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--output", default="zone-dashboard.html")
    args = parser.parse_args()
    if args.index < 0 or args.candles < 1 or args.candles > 500:
        parser.error("index must be nonnegative; candles must be between 1 and 500")
    from zone_energy.data import EngineResultsRepository, MarketDataRepository
    uri = os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/")
    results, market = EngineResultsRepository(uri,args.database), MarketDataRepository(uri,args.database)
    try:
        identity = json.dumps([args.run_id,"XAUUSD",args.timeframe,args.index],separators=(",",":"))
        document = results.get_checkpoint(identity)
        if document is None:
            raise ValueError("Checkpoint not found")
        context = document["replay_context"]
        values = dict(document["config"])
        values["timeframe"] = EngineTimeframe(values["timeframe"])
        values.setdefault("barrier_cost_transform", "power")
        config = EngineConfig(**values)
        bars = market.get_candles(args.timeframe,context["start"],context["end"])
        if len(bars) <= args.index or bars[args.index].datetime != context["candle_datetime"]:
            raise ValueError("Candle indexing differs from checkpoint")
        first = max(0,args.index-args.candles+1)
        candles = [{"index":i, "datetime":bars[i].datetime.isoformat(),
                    "open":bars[i].open,"high":bars[i].high,"low":bars[i].low,"close":bars[i].close}
                   for i in range(first,args.index+1)]
        data = dashboard_data(results.load_zones(identity),candles,config,args.index,document["year_candles"],args.run_id)
        actual = sorted([{"zone_id":z["id"],"energy":z["energy"]} for z in data["zones"]],key=lambda z:z["zone_id"])
        if actual != document["effective_zone_energies"]:
            raise ValueError("Checkpoint energies differ; dashboard withheld")
        output = Path(args.output).resolve()
        output.write_text(render_dashboard(data),encoding="utf-8")
        print("Checkpoint energy verification: MATCH")
        print(f"Zones: {len(data['zones'])}; candles: {first}–{args.index}; open movement: {data['open_move']}")
        print(f"Dashboard: {output}")
    finally:
        results.close()
        market.close()


if __name__ == "__main__":
    main()
