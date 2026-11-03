import os
import time
import requests
import psycopg
from dotenv import load_dotenv

load_dotenv()
API = "https://api.openf1.org/v1"
YEAR = int(os.getenv("F1_YEAR", "2025"))
COUNTRIES = {"Australia", "Bahrain", "Saudi Arabia", "United Arab Emirates"}
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
          dbname=os.getenv("DB_NAME", "f1_analytics"), user=os.getenv("DB_USER", "postgres"),
          password=os.getenv("DB_PASSWORD"))


def fetch(endpoint, **params):
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    time.sleep(float(os.getenv("OPENF1_DELAY", "0.25")))
    return data


def safe_fetch(endpoint, session_key):
    try:
        return fetch(endpoint, session_key=session_key)
    except requests.RequestException as exc:
        print(f"  WARNING: {endpoint} unavailable for session {session_key}: {exc}")
        return []


def as_bool(value):
    """Convert OpenF1 rainfall values (0/1, bool, or text) to PostgreSQL BOOLEAN."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "rain", "rainfall"}:
        return True
    if text in {"0", "false", "no", "", "none", "null"}:
        return False
    raise ValueError(f"Unexpected rainfall value: {value!r}")


def as_numeric_gap(value):
    """Return numeric time gaps; OpenF1 lap gaps such as '+1 LAP' are not numeric."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text or "lap" in text.lower():
        return None
    text = text.replace("+", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def main():
    all_sessions = fetch("sessions", year=YEAR)
    races = sorted((s for s in all_sessions if s.get("session_type") == "Race" and
                    s.get("country_name") in COUNTRIES), key=lambda s: s.get("date_start") or "")
    if not races:
        raise RuntimeError(f"No {YEAR} race sessions found for {sorted(COUNTRIES)}")

    # Keep all four selected races; do not accidentally import only the latest session.
    for session in races:
        skey = session["session_key"]
        print(f"\nImporting {session.get('session_name')} | {session.get('country_name')} | session_key={skey}")
        drivers = safe_fetch("drivers", skey)
        laps = safe_fetch("laps", skey)
        stints = safe_fetch("stints", skey)
        pits = safe_fetch("pit", skey)
        weather = safe_fetch("weather", skey)
        control = safe_fetch("race_control", skey)
        results = safe_fetch("session_result", skey)

        race_order = sorted((s for s in all_sessions if s.get("session_type") == "Race"),
                            key=lambda s: s.get("date_start") or "")
        round_no = next((i for i, s in enumerate(race_order, 1) if s.get("session_key") == skey), None)
        with psycopg.connect(**DB) as conn:
            with conn.cursor() as cur:
                circuit_name = session.get("circuit_short_name") or session.get("location") or "Unknown"
                cur.execute("SELECT circuit_id FROM circuits WHERE circuit_name=%s AND country IS NOT DISTINCT FROM %s",
                            (circuit_name, session.get("country_name")))
                row = cur.fetchone()
                if row:
                    circuit_id = row[0]
                else:
                    cur.execute("INSERT INTO circuits(circuit_name,country,circuit_location) VALUES (%s,%s,%s) RETURNING circuit_id",
                                (circuit_name, session.get("country_name"), session.get("location")))
                    circuit_id = cur.fetchone()[0]
                race_name = f"{YEAR} {session.get('country_name')} Grand Prix"
                race_date = (session.get("date_start") or "")[:10] or None
                cur.execute("""INSERT INTO races(season,round_number,race_name,circuit_id,race_date)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT (season,round_number) DO UPDATE SET
                    race_name=EXCLUDED.race_name,circuit_id=EXCLUDED.circuit_id,race_date=EXCLUDED.race_date
                    RETURNING race_id""", (YEAR, round_no, race_name, circuit_id, race_date))
                race_id = cur.fetchone()[0]
                cur.execute("""INSERT INTO sessions(race_id,session_type,session_date,source_session_key,status)
                    VALUES (%s,%s,%s,%s,'completed') ON CONFLICT (source_session_key) DO UPDATE SET
                    race_id=EXCLUDED.race_id,session_type=EXCLUDED.session_type,session_date=EXCLUDED.session_date
                    RETURNING session_id""", (race_id, session.get("session_type"), session.get("date_start"), skey))
                session_id = cur.fetchone()[0]

                # Rebuild session-scoped records so repeated imports are clean/idempotent.
                cur.execute("DELETE FROM pit_stops WHERE session_driver_id IN (SELECT session_driver_id FROM session_drivers WHERE session_id=%s)", (session_id,))
                cur.execute("DELETE FROM tyre_stints WHERE session_driver_id IN (SELECT session_driver_id FROM session_drivers WHERE session_id=%s)", (session_id,))
                for table in ("weather_samples", "race_control_events"):
                    cur.execute(f"DELETE FROM {table} WHERE session_id=%s", (session_id,))

                driver_map, driver_id_map = {}, {}
                for d in drivers:
                    num = d.get("driver_number")
                    if num is None: continue
                    num = int(num)
                    code = d.get("name_acronym")
                    name = d.get("full_name") or d.get("broadcast_name") or f"Driver {num}"
                    team = d.get("team_name") or "Unknown"
                    cur.execute("SELECT driver_id FROM drivers WHERE driver_number=%s AND driver_code IS NOT DISTINCT FROM %s",
                                (num, code))
                    existing = cur.fetchone()
                    if existing:
                        driver_id = existing[0]
                        cur.execute("UPDATE drivers SET driver_name=%s WHERE driver_id=%s", (name, driver_id))
                    else:
                        cur.execute("INSERT INTO drivers(driver_number,driver_code,driver_name) VALUES (%s,%s,%s) RETURNING driver_id",
                                    (num, code, name))
                        driver_id = cur.fetchone()[0]
                    driver_id_map[num] = driver_id
                    cur.execute("INSERT INTO teams(team_name) VALUES (%s) ON CONFLICT(team_name) DO NOTHING", (team,))
                    cur.execute("SELECT team_id FROM teams WHERE team_name=%s", (team,))
                    team_id = cur.fetchone()[0]
                    cur.execute("""INSERT INTO session_drivers(session_id,driver_id,team_id)
                        VALUES (%s,%s,%s) ON CONFLICT(session_id,driver_id) DO UPDATE SET team_id=EXCLUDED.team_id
                        RETURNING session_driver_id""", (session_id, driver_id, team_id))
                    driver_map[num] = cur.fetchone()[0]

                for lap in laps:
                    num, lap_no = lap.get("driver_number"), lap.get("lap_number")
                    sd_id = driver_map.get(int(num)) if num is not None else None
                    if sd_id is None or lap_no is None: continue
                    duration = lap.get("lap_duration")
                    valid = bool(duration and duration > 0 and not lap.get("is_pit_out_lap"))
                    cur.execute("""INSERT INTO laps(session_driver_id,lap_number,lap_time_seconds,sector1_seconds,
                        sector2_seconds,sector3_seconds,speed_trap_kmh,is_valid)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(session_driver_id,lap_number) DO UPDATE SET
                        lap_time_seconds=EXCLUDED.lap_time_seconds,sector1_seconds=EXCLUDED.sector1_seconds,
                        sector2_seconds=EXCLUDED.sector2_seconds,sector3_seconds=EXCLUDED.sector3_seconds,
                        speed_trap_kmh=EXCLUDED.speed_trap_kmh,is_valid=EXCLUDED.is_valid""",
                        (sd_id, lap_no, duration, lap.get("duration_sector_1"), lap.get("duration_sector_2"),
                         lap.get("duration_sector_3"), lap.get("st_speed"), valid))

                for row in stints:
                    num = row.get("driver_number")
                    sd_id = driver_map.get(int(num)) if num is not None else None
                    start_lap = row.get("lap_start")
                    end_lap = row.get("lap_end")
                    if sd_id is None or row.get("stint_number") is None:
                        continue
                    if start_lap is None or int(start_lap) < 1:
                        print(f"Skipping stint with invalid start lap: {row}")
                        continue
                    if end_lap is not None and int(end_lap) < int(start_lap):
                        print(f"Skipping malformed stint boundary: driver={num}, "
                              f"stint={row.get('stint_number')}, start={start_lap}, end={end_lap}")
                        continue
                    cur.execute("""INSERT INTO tyre_stints(session_driver_id,stint_number,compound,start_lap,end_lap,starting_tyre_age)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(session_driver_id,stint_number) DO UPDATE SET
                        compound=EXCLUDED.compound,start_lap=EXCLUDED.start_lap,end_lap=EXCLUDED.end_lap,
                        starting_tyre_age=EXCLUDED.starting_tyre_age""",
                        (sd_id, row.get("stint_number"), row.get("compound"), int(start_lap),
                         int(end_lap) if end_lap is not None else None, row.get("tyre_age_at_start")))

                counts = {}
                for row in sorted(pits, key=lambda x: (int(x.get("driver_number") or 0), x.get("lap_number") or 0, x.get("date") or "")):
                    num = row.get("driver_number")
                    sd_id = driver_map.get(int(num)) if num is not None else None
                    if sd_id is None: continue
                    counts[num] = counts.get(num, 0) + 1
                    stop_no = row.get("stop_number") or counts[num]
                    cur.execute("""INSERT INTO pit_stops(session_driver_id,lap_number,stop_number,lane_duration_seconds,
                        stop_duration_seconds,pit_timestamp) VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(session_driver_id,stop_number) DO UPDATE SET lap_number=EXCLUDED.lap_number,
                        lane_duration_seconds=EXCLUDED.lane_duration_seconds,stop_duration_seconds=EXCLUDED.stop_duration_seconds,
                        pit_timestamp=EXCLUDED.pit_timestamp""",
                        (sd_id, row.get("lap_number"), stop_no, row.get("lane_duration"), row.get("stop_duration"), row.get("date")))

                for w in weather:
                    cur.execute("""INSERT INTO weather_samples(session_id,recorded_at,air_temperature,track_temperature,
                        humidity,rainfall,wind_speed) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (session_id, w.get("date"), w.get("air_temperature"), w.get("track_temperature"),
                         w.get("humidity"), as_bool(w.get("rainfall")), w.get("wind_speed")))
                for rc in control:
                    num = rc.get("driver_number")
                    driver_id = driver_id_map.get(int(num)) if num is not None else None
                    cur.execute("""INSERT INTO race_control_events(session_id,driver_id,recorded_at,lap_number,
                        category,flag,scope,message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (session_id, driver_id, rc.get("date"), rc.get("lap_number"), rc.get("category"),
                         rc.get("flag"), rc.get("scope"), rc.get("message")))

                # Official classification, including DNF/DNS/DSQ flags.
                for result in results:
                    num = result.get("driver_number")
                    sd_id = driver_map.get(int(num)) if num is not None else None
                    if sd_id is None: continue
                    cur.execute("""INSERT INTO session_results(session_driver_id,grid_position,final_position,number_of_laps,
                        duration_seconds,gap_to_leader,dnf,dns,dsq) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(session_driver_id) DO UPDATE SET grid_position=EXCLUDED.grid_position,
                        final_position=EXCLUDED.final_position,number_of_laps=EXCLUDED.number_of_laps,
                        duration_seconds=EXCLUDED.duration_seconds,gap_to_leader=EXCLUDED.gap_to_leader,
                        dnf=EXCLUDED.dnf,dns=EXCLUDED.dns,dsq=EXCLUDED.dsq""",
                        (sd_id, result.get("grid_position"), result.get("position"), result.get("number_of_laps"),
                         result.get("duration"), as_numeric_gap(result.get("gap_to_leader")), bool(result.get("dnf")),
                         bool(result.get("dns")), bool(result.get("dsq"))))
                print(f"  session_id={session_id}; drivers={len(driver_map)}; laps={len(laps)}; "
                      f"stints={len(stints)}; pits={len(pits)}; weather={len(weather)}; control={len(control)}; results={len(results)}")
    print("Import finished.")

if __name__ == "__main__":
    main()
