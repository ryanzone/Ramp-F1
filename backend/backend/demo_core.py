"""Historical fetching, immutable raw snapshots, and lap quality checks."""
import hashlib
import json
import math
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError
load_dotenv()
ENDPOINTS = {'sessions', 'meetings', 'drivers', 'laps', 'stints', 'pit', 'position', 'intervals', 'weather', 'race_control', 'overtakes', 'session_result'}
_lock = threading.Lock()
_last = 0.0

def root():
    return Path(__file__).resolve().parent / 'demo_data'

class UpstreamError(RuntimeError):
    pass

def fetch(endpoint, **params):
    """One process-wide request lane; conservative 25/min, bounded retries."""
    global _last
    if endpoint not in ENDPOINTS:
        raise ValueError('Unsupported endpoint')
    url = os.getenv('OPENF1_BASE_URL', 'https://api.openf1.org/v1').rstrip('/') + '/' + endpoint
    with _lock:
        for attempt in range(4):
            time.sleep(max(0, 2.4 - (time.monotonic() - _last)))
            _last = time.monotonic()
            try:
                response = httpx.get(url, params=params, timeout=60)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        try: delay = float(response.headers.get('Retry-After', 2 ** attempt))
                        except ValueError: delay = 2 ** attempt
                        time.sleep(min(60, max(0, delay)))
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or not all(isinstance(r, dict) for r in payload):
                    raise UpstreamError('Expected a JSON array of objects')
                break
            except httpx.TransportError as exc:
                if attempt == 3: raise UpstreamError('OpenF1 connection failed') from exc
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise UpstreamError(f'OpenF1 request failed: {getattr(response, "status_code", "invalid JSON")}') from exc
        fetched = datetime.now(timezone.utc).isoformat()
        envelope = dict(endpoint=endpoint, params=params, fetched_at=fetched, payload=payload)
        encoded = json.dumps(envelope, ensure_ascii=False, allow_nan=False, indent=2)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        folder = root() / 'raw'; folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{endpoint}_{digest[:20]}.json'
        path.write_text(encoded, encoding='utf-8')
        return payload, str(path)

def historical(session):
    if session.get('is_cancelled'):
        raise ValueError('Session is cancelled')
    end = datetime.fromisoformat(session['date_end'].replace('Z', '+00:00'))
    if end.tzinfo is None or end + timedelta(minutes=30) >= datetime.now(timezone.utc):
        raise ValueError('Choose a completed historical session, at least 30 minutes after its end')

class Lap(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True, allow_inf_nan=False)
    session_key: int = Field(gt=0)
    driver_number: int = Field(gt=0)
    lap_number: int = Field(gt=0)
    lap_duration: float | None = Field(default=None, gt=0)
    duration_sector_1: float | None = Field(default=None, gt=0)
    duration_sector_2: float | None = Field(default=None, gt=0)
    duration_sector_3: float | None = Field(default=None, gt=0)
    st_speed: float | None = Field(default=None, ge=0)
    is_pit_out_lap: bool | None = None

def clean_laps(rows, session_key, driver_numbers):
    accepted, rejected, seen = [], [], set()
    for index, raw in enumerate(rows):
        try:
            lap = Lap.model_validate(raw)
            if lap.session_key != session_key: raise ValueError('Wrong session')
            if lap.driver_number not in driver_numbers: raise ValueError('Unknown session driver')
            key = (lap.driver_number, lap.lap_number)
            if key in seen: raise ValueError('Duplicate driver/lap')
            seen.add(key)
            row = lap.model_dump()
            # This is analytical suitability, NOT official FIA lap validity.
            row['is_valid'] = lap.lap_duration is not None and lap.is_pit_out_lap is False
            accepted.append(row)
        except (ValidationError, ValueError) as exc:
            rejected.append({'index': index, 'reason': str(exc), 'record': raw})
    return accepted, rejected

def ingest(session_key, extras=()):
    sessions, session_file = fetch('sessions', session_key=session_key)
    if len(sessions) != 1: raise ValueError('Expected exactly one session')
    session = sessions[0]; historical(session)
    if session.get('session_name') != 'Race': raise ValueError('This milestone selects Race sessions only')
    files = [session_file]
    meetings, path = fetch('meetings', meeting_key=session['meeting_key']); files.append(path)
    if len(meetings) != 1: raise ValueError('Expected exactly one meeting')
    drivers, path = fetch('drivers', session_key=session_key); files.append(path)
    numbers = set()
    for driver in drivers:
        number = driver.get('driver_number')
        if type(number) is not int or number <= 0 or number in numbers or driver.get('session_key') != session_key or not driver.get('full_name'):
            raise ValueError('Invalid or duplicate session driver; raw response retained')
        numbers.add(number)
    if not drivers: raise ValueError('No drivers returned; raw response retained')
    laps, path = fetch('laps', session_key=session_key); files.append(path)
    clean, rejected = clean_laps(laps, session_key, numbers)
    if not clean: raise ValueError('No usable lap records; raw responses retained')
    for endpoint in extras:
        if endpoint not in ENDPOINTS - {'sessions', 'meetings', 'drivers', 'laps'}: raise ValueError('Unsupported extra endpoint')
        _, path = fetch(endpoint, session_key=session_key); files.append(path)
    bundle = dict(session=session, meeting=meetings[0], drivers=drivers, laps=clean, rejected_laps=rejected, raw_files=[Path(f).name for f in files])
    folder = root() / 'processed'; folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{session_key}.json'
    temporary = path.with_suffix('.tmp'); temporary.write_text(json.dumps(bundle, indent=2, allow_nan=False), encoding='utf-8'); temporary.replace(path)
    return dict(session_key=session_key, drivers=len(drivers), laps=len(clean), rejected_laps=len(rejected), bundle=str(path))

def bundle(session_key):
    return json.loads((root() / 'processed' / f'{session_key}.json').read_text(encoding='utf-8'))
