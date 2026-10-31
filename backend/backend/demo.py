"""Role A demo: python -m backend.demo fetch | load."""
import argparse
import json
from pathlib import Path
from backend import demo_core as core

def load():
    # Reuse the team's schema-compatible importer with validated saved inputs.
    from backend import demo_loader as importer
    from psycopg.types.json import Jsonb
    key=json.loads((core.root()/'active.json').read_text())['session_key']
    b = core.bundle(key)
    importer.YEAR=b['session']['year']
    importer.RACE_COUNTRY=b['session']['country_name']
    core.historical(b['session'])
    def saved_fetch(endpoint, **params):
        if endpoint == 'sessions':
            # Preserve the team's round calculation with the full season list.
            return [b['session']]
        if endpoint == 'drivers': return b['drivers']
        if endpoint == 'laps': return b['laps']
        raise ValueError(endpoint)
    importer.fetch = saved_fetch
    importer.main()
    # Record provenance and analytical suitability omitted by the original importer.
    from backend.main import get_connection
    with get_connection() as conn:
        sid = conn.execute('SELECT session_id FROM sessions WHERE source_session_key=%s',(key,)).fetchone()['session_id']
        for r in b['laps']:
            conn.execute('UPDATE laps l SET is_valid=%s FROM session_drivers sd, drivers d WHERE l.session_driver_id=sd.session_driver_id AND sd.driver_id=d.driver_id AND sd.session_id=%s AND d.driver_number=%s AND l.lap_number=%s', (r['is_valid'],sid,r['driver_number'],r['lap_number']))
        for name in b['raw_files']:
            raw=json.loads((core.root()/'raw'/name).read_text())
            conn.execute('INSERT INTO raw_api_data(session_id,endpoint,fetched_at,payload) SELECT %s,%s,%s,%s WHERE NOT EXISTS (SELECT 1 FROM raw_api_data WHERE session_id=%s AND endpoint=%s AND payload=%s)',(sid,raw['endpoint'],raw['fetched_at'],Jsonb(raw['payload']),sid,raw['endpoint'],Jsonb(raw['payload'])))

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['fetch','load']); args=parser.parse_args()
    if args.action=='fetch':
        print(json.dumps(core.ingest(9839),indent=2))
        (core.root()/'active.json').write_text(json.dumps({'session_key':9839}))
    else: load()
if __name__=='__main__': main()
