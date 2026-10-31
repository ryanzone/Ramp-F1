import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from backend import demo_core as core
router=APIRouter()
def data():
    try: return core.bundle(json.loads((core.root()/'active.json').read_text())['session_key'])
    except FileNotFoundError: raise HTTPException(503,'Run python -m backend.demo fetch first')
@router.get('/api/demo/summary')
def summary():
    b=data()
    return {'source':'Saved historical OpenF1 snapshot', 'session':b['session'], 'drivers':len(b['drivers']), 'laps':len(b['laps']), 'rejected_laps':len(b['rejected_laps'])}
@router.get('/api/demo/drivers')
def drivers():
    return [{'driver_number':d['driver_number'],'driver_code':d.get('name_acronym'),'driver_name':d['full_name'],'team_name':d.get('team_name')} for d in data()['drivers']]
@router.get('/api/demo/laps')
def laps(driver_number:int|None=None,limit:int=Query(100,ge=1,le=2000)):
    rows=data()['laps']
    if driver_number is not None: rows=[r for r in rows if r['driver_number']==driver_number]
    return {'total':len(rows),'items':rows[:limit]}
@router.get('/demo',response_class=HTMLResponse)
def page():
    return """<!doctype html><html><meta charset='utf-8'><title>RAMP â€” Role A demo</title>
<style>body{background:#111827;color:#eee;font:17px system-ui;max-width:1000px;margin:50px auto;padding:20px}select{padding:10px}td,th{padding:10px;text-align:left;border-bottom:1px solid #374151}a{color:#93c5fd}</style>
<h1>RAMP Â· Historical data demo</h1><p>2025 Abu Dhabi Â· OpenF1 â†’ validation â†’ saved data â†’ FastAPI</p>
<p>This page uses a real saved snapshot. The team's React dashboard remains a separate illustrative prototype.</p>
<p id='status'>Loadingâ€¦</p><label>Driver <select id='driver'></select></label><table><thead><tr><th>Lap</th><th>Time (seconds)</th><th>Pace eligible</th></tr></thead><tbody id='laps'></tbody></table><p><a href='/docs'>API documentation</a></p>
<script>
async function get(url){const r=await fetch(url);if(!r.ok)throw Error('API unavailable â€” run the fetch command.');return r.json()}
async function show(){try{const r=await get('/api/demo/laps?driver_number='+document.querySelector('#driver').value);const body=document.querySelector('#laps');body.replaceChildren();for(const x of r.items){const tr=document.createElement('tr');for(const v of [x.lap_number,x.lap_duration??'Missing',x.is_valid?'Yes':'No']){const td=document.createElement('td');td.textContent=v;tr.append(td)}body.append(tr)}}catch(e){document.querySelector('#status').textContent=e.message}}
(async()=>{try{const s=await get('/api/demo/summary');document.querySelector('#status').textContent=`${s.session.year} ${s.session.country_name} · ${s.drivers} drivers Â· ${s.laps} accepted laps Â· ${s.rejected_laps} rejected records`;for(const d of await get('/api/demo/drivers')){const o=document.createElement('option');o.value=d.driver_number;o.textContent=d.driver_name;document.querySelector('#driver').append(o)}document.querySelector('#driver').onchange=show;await show()}catch(e){document.querySelector('#status').textContent=e.message}})();
</script></html>"""
