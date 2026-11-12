"""Question -> SQL templates (no LLM).

Every supported question type is an `Intent`: trigger patterns, the entities it needs,
a parameterised SQL template over the time-bounded `replay.*` views, and an explanation
function that turns the *returned rows* into a sentence. Values (drivers, counts,
patterns) are bound parameters, never pasted into SQL text; the only text that varies is
fixed fragments chosen in code (e.g. ASC/DESC). Every template is validated like any other
query before it runs (sql_validator.py) and can only see data up to the replay clock.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

CLEAN_FACTOR = 1.07      # laps slower than 107% of a driver's own best (safety car, traffic, pit) are ignored


@dataclass
class Entities:
    drivers: list[dict] = field(default_factory=list)     # roster rows: driver_code, driver_name, team_name, driver_number
    teams: list[str] = field(default_factory=list)
    n: int | None = None
    minutes: int | None = None
    compound: str | None = None
    limit: int | None = None
    flags: set[str] = field(default_factory=set)           # e.g. 'lost' for "lost positions"

    def code(self, i: int = 0) -> str | None:
        return self.drivers[i]['driver_code'] if len(self.drivers) > i else None


@dataclass
class Built:
    sql: str
    params: dict
    chart: dict | None = None


@dataclass
class Intent:
    name: str
    title: str
    examples: list[str]
    how: str                                   # plain-language description of the SQL technique
    triggers: list[str]                        # regexes searched in the lower-cased question
    build: Callable[[Entities], Built]
    explain: Callable[[list[dict], Entities], str]
    needs_drivers: int = 0
    needs_team: bool = False
    note: str | None = None                    # data limitation shown with the answer
    patterns: list = field(init=False)

    def __post_init__(self):
        self.patterns = [re.compile(t) for t in self.triggers]


# ---- helpers ---------------------------------------------------------------------------
def f(x, digits=3):
    return 'n/a' if x is None else f'{x:.{digits}f}'


def lap_time(x):
    if x is None:
        return 'n/a'
    m = int(x // 60)
    return f'{m}:{x - 60 * m:06.3f}' if m else f'{x:.3f}s'


def names(rows, key='driver_code', k=3):
    return ', '.join(str(r[key]) for r in rows[:k])


EMPTY = 'Nothing to report yet at this point of the replay.'

# Shared CTE: the driver's valid laps that are close to their own best (drops safety-car, in/out laps).
CLEAN = f"""base AS (
    SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds
    FROM laps WHERE is_valid AND lap_time_seconds IS NOT NULL),
clean AS (
    SELECT * FROM (SELECT b.*, MIN(lap_time_seconds) OVER (PARTITION BY driver_code) AS best FROM base b) x
    WHERE lap_time_seconds <= best * :clean_factor)"""
CLEAN_PARAMS = {'clean_factor': CLEAN_FACTOR}

CUR_STATE = """cur AS (
    SELECT cp.session_driver_id, cp.driver_code, cp.driver_name, cp.position, cp.interval_ahead_seconds,
           st.compound, COALESCE(st.starting_tyre_age, 0) + st.laps_completed AS tyre_age, dp.avg_last5
    FROM current_positions cp
    JOIN current_stints st ON st.session_driver_id = cp.session_driver_id
    LEFT JOIN driver_pace dp ON dp.session_driver_id = cp.session_driver_id
    WHERE cp.position IS NOT NULL)"""


# ---- 1. standings -----------------------------------------------------------------------
def build_standings(e):
    n = e.n or e.limit or 22
    return Built("""SELECT position, driver_code, driver_name, team_name,
                           gap_to_leader_seconds AS gap_to_leader, interval_ahead_seconds AS interval_ahead
                    FROM current_positions WHERE position IS NOT NULL ORDER BY position LIMIT :limit""",
                 {'limit': n}, {'type': 'table'})


def explain_standings(rows, e):
    if not rows:
        return EMPTY
    top = rows[0]
    out = f"{top['driver_code']} ({top['team_name']}) leads"
    if len(rows) > 1:
        out += f", then {names(rows[1:], k=2)}"
        if rows[1]['gap_to_leader'] is not None:
            out += f"; {rows[1]['driver_code']} is {f(rows[1]['gap_to_leader'], 1)}s behind"
    return out + '.'


# ---- 2. fastest average pace ------------------------------------------------------------
def build_fastest_avg(e):
    return Built(f"""WITH {CLEAN}
        SELECT RANK() OVER (ORDER BY AVG(lap_time_seconds)) AS pace_rank, driver_code, driver_name, team_name,
               COUNT(*) AS laps_used, ROUND(AVG(lap_time_seconds), 3) AS avg_lap, MIN(lap_time_seconds) AS best_lap
        FROM clean GROUP BY driver_code, driver_name, team_name
        HAVING COUNT(*) >= :min_laps AND COUNT(*) >= 0.5 * (SELECT MAX(lap_number) FROM laps)
        ORDER BY pace_rank LIMIT :limit""",
                 {**CLEAN_PARAMS, 'min_laps': 3, 'limit': e.n or e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['avg_lap'], 'title': 'Average clean lap (s)'})


def explain_fastest_avg(rows, e):
    if not rows:
        return 'No driver has three clean laps yet.'
    a = rows[0]
    out = f"{a['driver_code']} has the fastest average lap time: {f(a['avg_lap'])}s over {a['laps_used']} clean laps"
    if len(rows) > 1:
        out += f", {f(rows[1]['avg_lap'] - a['avg_lap'])}s ahead of {rows[1]['driver_code']}"
    return out + '. Clean laps are valid laps within 107% of the driver\'s own best.'


# ---- 3. pace over the last N laps -------------------------------------------------------
def build_recent_pace(e):
    n = e.n or 5
    return Built(f"""WITH {CLEAN},
        ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY driver_code ORDER BY lap_number DESC) AS recency FROM clean)
        SELECT RANK() OVER (ORDER BY AVG(lap_time_seconds)) AS pace_rank, driver_code, driver_name, team_name,
               COUNT(*) AS laps_used, ROUND(AVG(lap_time_seconds), 3) AS avg_last_n,
               MIN(lap_time_seconds) AS best_in_window, MAX(lap_number) AS latest_lap
        FROM ranked WHERE recency <= :n
        GROUP BY driver_code, driver_name, team_name
        HAVING COUNT(*) >= :min_laps AND MAX(lap_number) >= (SELECT MAX(lap_number) FROM laps) - 3
        ORDER BY pace_rank LIMIT :limit""",
                 {**CLEAN_PARAMS, 'n': n, 'min_laps': min(3, n), 'limit': e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['avg_last_n'], 'title': f'Average of last {n} clean laps (s)'})


def explain_recent_pace(rows, e):
    if not rows:
        return 'Not enough clean laps yet.'
    a = rows[0]
    out = (f"{a['driver_code']} has the strongest pace over their last {a['laps_used']} clean laps: "
           f"{f(a['avg_last_n'])}s average")
    if len(rows) > 1:
        out += f", {f(rows[1]['avg_last_n'] - a['avg_last_n'])}s better than {rows[1]['driver_code']}"
    return out + '.'


# ---- 4. consistency ---------------------------------------------------------------------
def build_consistency(e):
    return Built(f"""WITH {CLEAN}
        SELECT RANK() OVER (ORDER BY STDDEV_SAMP(lap_time_seconds)) AS consistency_rank, driver_code, driver_name,
               team_name, COUNT(*) AS laps_used, ROUND(STDDEV_SAMP(lap_time_seconds), 3) AS lap_stddev,
               ROUND(AVG(lap_time_seconds), 3) AS avg_lap
        FROM clean GROUP BY driver_code, driver_name, team_name
        HAVING COUNT(*) >= :min_laps AND COUNT(*) >= 0.5 * (SELECT MAX(lap_number) FROM laps)
        ORDER BY consistency_rank LIMIT :limit""",
                 {**CLEAN_PARAMS, 'min_laps': 5, 'limit': e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['lap_stddev'], 'title': 'Lap-time spread, std dev (s)'})


def explain_consistency(rows, e):
    if not rows:
        return 'No driver has five clean laps yet.'
    a = rows[0]
    return (f"{a['driver_code']} has been the most consistent: lap times vary by only {f(a['lap_stddev'])}s "
            f"(standard deviation) over {a['laps_used']} clean laps.")


# ---- 5. positions gained / lost -----------------------------------------------------------
def build_positions_gained(e):
    lost = 'lost' in e.flags
    order = 'ASC' if lost else 'DESC'
    return Built(f"""WITH ordered AS (
            SELECT session_driver_id, position, ROW_NUMBER() OVER (PARTITION BY session_driver_id ORDER BY recorded_at) AS rn
            FROM positions WHERE position IS NOT NULL)
        SELECT RANK() OVER (ORDER BY (o.position - c.position) {order}) AS change_rank, c.driver_code, c.driver_name,
               c.team_name, o.position AS first_recorded_position, c.position AS current_position,
               o.position - c.position AS positions_gained
        FROM ordered o JOIN current_positions c ON c.session_driver_id = o.session_driver_id
        WHERE o.rn = 1 AND c.position IS NOT NULL
        ORDER BY change_rank, c.position LIMIT :limit""",
                 {'limit': e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['positions_gained'], 'title': 'Positions gained since the start'})


def explain_positions_gained(rows, e):
    if not rows:
        return EMPTY
    a = rows[0]
    g = a['positions_gained']
    if g == 0:
        return 'Nobody has changed position since the first recorded order.'
    verb = f"gained {g}" if g > 0 else f"lost {-g}"
    return (f"{a['driver_code']} has {verb} position{'s' if abs(g) != 1 else ''}, from P{a['first_recorded_position']} "
            f"(first recorded position) to P{a['current_position']}.")


def explain_qualifying_vs_race(rows, e):
    return ("Qualifying results are not stored in this database, so I compared each driver's first recorded race "
            "position with the current position instead. ") + explain_positions_gained(rows, e)


# ---- 6. compare two drivers ---------------------------------------------------------------
def build_compare(e):
    return Built("""WITH a AS (SELECT lap_number, lap_time_seconds FROM laps
                              WHERE driver_code = :a AND is_valid AND lap_time_seconds IS NOT NULL),
                     b AS (SELECT lap_number, lap_time_seconds FROM laps
                              WHERE driver_code = :b AND is_valid AND lap_time_seconds IS NOT NULL)
        SELECT COALESCE(a.lap_number, b.lap_number) AS lap_number, a.lap_time_seconds AS a_time,
               b.lap_time_seconds AS b_time, ROUND(a.lap_time_seconds - b.lap_time_seconds, 3) AS delta_a_minus_b
        FROM a FULL JOIN b ON a.lap_number = b.lap_number ORDER BY lap_number""",
                 {'a': e.code(0), 'b': e.code(1)},
                 {'type': 'line', 'x': 'lap_number', 'y': ['a_time', 'b_time'],
                  'labels': {'a_time': e.code(0), 'b_time': e.code(1)}, 'title': 'Lap time comparison (s)'})


def explain_compare(rows, e):
    a, b = e.code(0), e.code(1)
    both = [r for r in rows if r['a_time'] is not None and r['b_time'] is not None]
    if not both:
        return f'{a} and {b} have no common completed laps yet.'
    # Ignore laps far off either driver's pace (safety car, pit in/out) like the other pace answers.
    best_a, best_b = min(r['a_time'] for r in both), min(r['b_time'] for r in both)
    clean = [r for r in both if r['a_time'] <= best_a * CLEAN_FACTOR and r['b_time'] <= best_b * CLEAN_FACTOR] or both
    d = sum(r['delta_a_minus_b'] for r in clean) / len(clean)
    faster, slower = (a, b) if d < 0 else (b, a)
    ahead = sum(1 for r in clean if r['delta_a_minus_b'] < 0)
    return (f"Over {len(clean)} comparable laps {faster} is {f(abs(d))}s per lap faster than {slower} on average; "
            f"{a} was quicker on {ahead} of those laps and {b} on {len(clean) - ahead}. "
            f"Best laps: {a} {lap_time(best_a)}, {b} {lap_time(best_b)}.")


# ---- 7. tyres right now ---------------------------------------------------------------------
def build_tyres_now(e):
    where = 'WHERE UPPER(s.compound) = :compound ' if e.compound else ''
    params = {'compound': e.compound} if e.compound else {}
    return Built(f"""SELECT s.driver_code, s.driver_name, s.team_name, s.compound, s.stint_number, s.start_lap,
                           COALESCE(s.starting_tyre_age, 0) + s.laps_completed AS tyre_age_laps, c.position
                    FROM current_stints s LEFT JOIN current_positions c ON c.session_driver_id = s.session_driver_id
                    {where}ORDER BY s.compound, c.position""",
                 params, {'type': 'tyre_distribution', 'group': 'compound', 'title': 'Current tyre compounds'})


def explain_tyres_now(rows, e):
    if not rows:
        return f"No driver is on {e.compound.lower()} tyres right now." if e.compound else EMPTY
    counts = {}
    for r in rows:
        counts[r['compound']] = counts.get(r['compound'], 0) + 1
    split = ', '.join(f'{n} on {c.lower()}' for c, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    if e.compound:
        return f"{len(rows)} driver{'s' if len(rows) != 1 else ''} on {e.compound.lower()}s: {names(rows, k=8)}."
    return f'Current tyres: {split}.'


# ---- 8. tyre degradation -----------------------------------------------------------------------
def build_degradation(e):
    return Built("""WITH stint_laps AS (
            SELECT s.driver_code, s.driver_name, s.team_name, s.compound, l.lap_time_seconds, l.lap_number, l.lap_number - s.start_lap AS stint_lap
            FROM current_stints s
            JOIN laps l ON l.session_driver_id = s.session_driver_id AND l.lap_number >= s.start_lap
                       AND l.is_valid AND l.lap_time_seconds IS NOT NULL
            JOIN driver_pace p ON p.session_driver_id = s.session_driver_id
            WHERE l.lap_time_seconds <= p.best_lap * :clean_factor)
        SELECT RANK() OVER (ORDER BY REGR_SLOPE(lap_time_seconds, stint_lap) DESC) AS degradation_rank, driver_code,
               driver_name, team_name, compound, COUNT(*) AS laps_in_stint,
               ROUND(CAST(REGR_SLOPE(lap_time_seconds, stint_lap) AS NUMERIC), 3) AS seconds_per_lap
        FROM stint_laps GROUP BY driver_code, driver_name, team_name, compound
        HAVING COUNT(*) >= :min_laps AND MAX(lap_number) >= (SELECT MAX(lap_number) FROM laps) - 3
        ORDER BY degradation_rank LIMIT :limit""",
                 {**CLEAN_PARAMS, 'min_laps': 5, 'limit': e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['seconds_per_lap'], 'title': 'Lap-time trend in current stint (s per lap)'})


def explain_degradation(rows, e):
    if not rows:
        return 'No driver has five clean laps in their current stint yet.'
    a = rows[0]
    s = a['seconds_per_lap']
    out = (f"{a['driver_code']} shows the highest degradation: lap times are changing by {f(s)}s per lap "
           f"over {a['laps_in_stint']} laps on {a['compound'].lower()}s")
    return out + ('.' if s > 0 else ', so nobody is slowing yet.') + \
        ' (Trend of lap time against stint lap; it also includes the fuel-burn effect.)'


# ---- 9. undercut candidates ----------------------------------------------------------------------
def build_undercut(e):
    return Built(f"""WITH {CUR_STATE}
        SELECT ch.driver_code AS chaser, ah.driver_code AS car_ahead, ch.position AS chaser_position,
               ch.interval_ahead_seconds AS gap_to_car_ahead, ch.compound AS chaser_tyre, ch.tyre_age AS chaser_tyre_age,
               ah.compound AS ahead_tyre, ah.tyre_age AS ahead_tyre_age
        FROM cur ch JOIN cur ah ON ah.position = ch.position - 1
        WHERE ch.interval_ahead_seconds <= :gap AND ch.tyre_age >= :min_age AND ch.tyre_age >= ah.tyre_age
        ORDER BY ch.interval_ahead_seconds LIMIT :limit""",
                 {'gap': 2.5, 'min_age': 12, 'limit': e.limit or 10}, {'type': 'table'})


def explain_undercut(rows, e):
    if not rows:
        return ('No undercut candidates right now: nobody is within 2.5s of the car ahead on tyres at least '
                '12 laps old and not fresher than that car.')
    a = rows[0]
    return (f"{len(rows)} possible undercut{'s' if len(rows) != 1 else ''}. Best: {a['chaser']} is {f(a['gap_to_car_ahead'], 1)}s "
            f"behind {a['car_ahead']} on {a['chaser_tyre_age']}-lap-old {a['chaser_tyre'].lower()}s. "
            'Heuristic: within 2.5s of the car ahead, tyres at least 12 laps old and not fresher than that car.')


# ---- 10/11. tyre strategies -------------------------------------------------------------------------
def build_tyre_stints(e):
    return Built("""SELECT driver_code, team_name, stint_number, compound, start_lap,
                           COALESCE(end_lap, start_lap + laps_completed - 1) AS last_lap,
                           CASE WHEN end_lap IS NULL THEN 'running' ELSE 'finished' END AS status, laps_completed
                    FROM tyre_stints ORDER BY team_name, driver_code, stint_number""",
                 {}, {'type': 'tyre_stints', 'title': 'Tyre stints so far'})


def explain_tyre_stints(rows, e):
    if not rows:
        return EMPTY
    drivers = {r['driver_code'] for r in rows}
    stops = sum(1 for r in rows if r['stint_number'] > 1)
    return f'{len(drivers)} drivers have run {len(rows)} stints so far, with {stops} tyre changes after the start.'


def build_team_strategies(e):
    where = 'WHERE team_name ILIKE :t0 ' + ('OR team_name ILIKE :t1 ' if len(e.teams) > 1 else '') if e.teams else ''
    params = {f't{i}': f'%{t}%' for i, t in enumerate(e.teams[:2])}
    return Built(f"""SELECT team_name, driver_code, STRING_AGG(compound, ' > ' ORDER BY stint_number) AS strategy,
                            COUNT(*) AS stints, MAX(stint_number) - 1 AS stops_so_far, MAX(start_lap) AS latest_stint_start_lap
                     FROM tyre_stints {where}GROUP BY team_name, driver_code ORDER BY team_name, driver_code""",
                 params, {'type': 'table'})


def explain_team_strategies(rows, e):
    if not rows:
        return EMPTY
    teams: dict[str, list] = {}
    for r in rows:
        teams.setdefault(r['team_name'], []).append(r)
    parts = []
    for team, rs in list(teams.items())[:4]:
        parts.append(f"{team}: " + '; '.join(f"{r['driver_code']} {r['strategy'].title()}" for r in rs))
    more = f' (+{len(teams) - 4} more teams)' if len(teams) > 4 else ''
    return ' | '.join(parts) + more + '.'


# ---- 12-15. pit stops ---------------------------------------------------------------------------------
PIT_NOTE = ('OpenF1 pit data is incomplete in 2026: some stops have no stationary time and some stops are missing, '
            'so pit answers only cover recorded stops.')


def build_pit_team_avg(e):
    return Built("""SELECT RANK() OVER (ORDER BY AVG(stop_duration_seconds)) AS pit_rank, team_name,
                           COUNT(*) AS stops_recorded, ROUND(AVG(stop_duration_seconds), 3) AS avg_stop_seconds,
                           MIN(stop_duration_seconds) AS best_stop_seconds
                    FROM pit_stops WHERE stop_duration_seconds IS NOT NULL
                    GROUP BY team_name HAVING COUNT(*) >= 1 ORDER BY pit_rank""",
                 {}, {'type': 'bar', 'x': 'team_name', 'y': ['avg_stop_seconds'], 'title': 'Average stationary time (s)'})


def explain_pit_team_avg(rows, e):
    if not rows:
        return 'No pit stop with a measured stationary time has been recorded yet.'
    a = rows[0]
    return (f"{a['team_name']} has the fastest average stop: {f(a['avg_stop_seconds'], 2)}s over {a['stops_recorded']} "
            f"recorded stop{'s' if a['stops_recorded'] != 1 else ''} (best {f(a['best_stop_seconds'], 2)}s).")


def build_pit_counts(e):
    return Built("""SELECT d.driver_code, d.driver_name, d.team_name, COUNT(p.stop_number) AS recorded_stops,
                           COALESCE(MAX(s.stint_number), 1) - 1 AS stops_from_tyre_stints
                    FROM drivers d
                    LEFT JOIN pit_stops p ON p.session_driver_id = d.session_driver_id
                    LEFT JOIN current_stints s ON s.session_driver_id = d.session_driver_id
                    GROUP BY d.driver_code, d.driver_name, d.team_name
                    ORDER BY stops_from_tyre_stints DESC, recorded_stops DESC, d.driver_code""",
                 {}, {'type': 'bar', 'x': 'driver_code', 'y': ['stops_from_tyre_stints'], 'title': 'Pit stops completed'})


def explain_pit_counts(rows, e):
    if not rows:
        return EMPTY
    total = sum(r['stops_from_tyre_stints'] for r in rows)
    most = rows[0]
    return (f"{total} stop{'s' if total != 1 else ''} completed so far (counted from tyre changes). "
            f"Most: {most['driver_code']} with {most['stops_from_tyre_stints']}.")


def build_not_pitted(e):
    return Built("""SELECT d.driver_code, d.driver_name, d.team_name, c.position, s.compound,
                           COALESCE(s.starting_tyre_age, 0) + COALESCE(s.laps_completed, 0) AS tyre_age_laps
                    FROM drivers d
                    LEFT JOIN current_stints s ON s.session_driver_id = d.session_driver_id
                    LEFT JOIN current_positions c ON c.session_driver_id = d.session_driver_id
                    WHERE NOT EXISTS (SELECT 1 FROM pit_stops p WHERE p.session_driver_id = d.session_driver_id)
                      AND COALESCE(s.stint_number, 1) = 1
                    ORDER BY c.position, d.driver_code""",
                 {}, {'type': 'table'})


def explain_not_pitted(rows, e):
    if not rows:
        return 'Every driver has made at least one stop.'
    return f"{len(rows)} driver{'s have' if len(rows) != 1 else ' has'} not pitted yet: {names(rows, k=10)}."


def build_pit_time_lost(e):
    return Built("""SELECT team_name, driver_code, COUNT(*) AS stops, ROUND(SUM(lane_duration_seconds), 3) AS pit_lane_seconds,
                           ROUND(SUM(stop_duration_seconds), 3) AS stationary_seconds,
                           ROUND(AVG(lane_duration_seconds), 3) AS avg_lane_seconds
                    FROM pit_stops GROUP BY team_name, driver_code
                    ORDER BY pit_lane_seconds DESC NULLS LAST LIMIT :limit""",
                 {'limit': e.limit or 15}, {'type': 'bar', 'x': 'driver_code', 'y': ['pit_lane_seconds'], 'title': 'Time in the pit lane (s)'})


def explain_pit_time_lost(rows, e):
    if not rows or rows[0]['pit_lane_seconds'] is None:
        return 'No pit stop with a measured pit-lane time has been recorded yet.'
    a = rows[0]
    return (f"{a['driver_code']} has spent the most time in the pit lane: {f(a['pit_lane_seconds'], 1)}s over "
            f"{a['stops']} stop{'s' if a['stops'] != 1 else ''}. This is pit-lane time, not the full race time lost.")


# ---- 16. drivers losing time --------------------------------------------------------------------------------
def build_losing_time(e):
    return Built("""WITH v AS (
            SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds,
                   AVG(lap_time_seconds) OVER (PARTITION BY driver_code ORDER BY lap_number
                        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS baseline,
                   COUNT(lap_time_seconds) OVER (PARTITION BY driver_code ORDER BY lap_number
                        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS baseline_laps
            FROM laps WHERE is_valid AND lap_time_seconds IS NOT NULL)
        SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds, ROUND(baseline, 3) AS baseline,
               ROUND(lap_time_seconds - baseline, 3) AS time_lost_vs_baseline
        FROM v WHERE lap_number > (SELECT MAX(lap_number) FROM laps) - :n AND baseline_laps >= 3
          AND lap_time_seconds - baseline >= :threshold
        ORDER BY time_lost_vs_baseline DESC LIMIT :limit""",
                 {'n': e.n or 3, 'threshold': 1.0, 'limit': e.limit or 10},
                 {'type': 'bar', 'x': 'driver_code', 'y': ['time_lost_vs_baseline'], 'title': 'Time lost vs recent baseline (s)'})


def explain_losing_time(rows, e):
    if not rows:
        return 'No driver still racing has lost more than 1.0s against their recent baseline in the latest laps.'
    a = rows[0]
    return (f"{a['driver_code']} is losing the most time: lap {a['lap_number']} was {f(a['time_lost_vs_baseline'], 2)}s "
            f"slower than their rolling baseline ({f(a['baseline'])}s). {len(rows)} driver-lap"
            f"{'s' if len(rows) != 1 else ''} lost over 1.0s in the latest laps (pit laps and safety cars can cause this).")


# ---- 17. overtaking opportunities ---------------------------------------------------------------------------
def build_overtakes(e):
    return Built(f"""WITH {CUR_STATE}
        SELECT ch.driver_code AS attacker, ah.driver_code AS car_ahead, ch.position AS attacker_position,
               ch.interval_ahead_seconds AS gap_seconds, ch.avg_last5 AS attacker_pace_last5, ah.avg_last5 AS ahead_pace_last5,
               ROUND(ah.avg_last5 - ch.avg_last5, 3) AS pace_advantage_seconds
        FROM cur ch JOIN cur ah ON ah.position = ch.position - 1
        WHERE ch.interval_ahead_seconds <= :gap AND ah.avg_last5 - ch.avg_last5 >= :min_adv
        ORDER BY ch.interval_ahead_seconds LIMIT :limit""",
                 {'gap': 1.5, 'min_adv': 0.2, 'limit': e.limit or 10}, {'type': 'table'})


def explain_overtakes(rows, e):
    if not rows:
        return 'No overtaking opportunities: nobody is within 1.5s of the car ahead with at least 0.2s per lap pace advantage.'
    a = rows[0]
    return (f"{a['attacker']} could attack {a['car_ahead']}: {f(a['gap_seconds'], 1)}s behind and "
            f"{f(a['pace_advantage_seconds'], 2)}s per lap quicker over the last five laps. "
            f"{len(rows)} opportunit{'ies' if len(rows) != 1 else 'y'} in total.")


# ---- 18-19. penalties and stewards -----------------------------------------------------------------------------
RULING = """CASE WHEN message ILIKE '%penalty served%' THEN 'penalty served'
                  WHEN message ILIKE '%penalty for%' THEN 'penalty'
                  WHEN message ILIKE '%no further%' THEN 'no further action'
                  WHEN message ILIKE '%investigat%' THEN 'investigation'
                  WHEN message ILIKE '%deleted%' THEN 'lap time deleted'
                  WHEN message ILIKE '%noted%' THEN 'noted'
                  ELSE 'other' END"""


def build_penalty_reason(e):
    d = e.drivers[0]
    return Built(f"""SELECT recorded_at, lap_number, {RULING} AS ruling, message
        FROM race_control
        WHERE (message ILIKE :code_pat OR message ILIKE :car_pat)
          AND (message ILIKE '%penalty%' OR message ILIKE '%investigat%' OR message ILIKE '%incident%'
               OR message ILIKE '%deleted%' OR message ILIKE '%noted%' OR message ILIKE '%reprimand%'
               OR message ILIKE '%no further%' OR flag = 'BLACK AND WHITE')
        ORDER BY recorded_at""",
                 {'code_pat': f"%({d['driver_code']})%", 'car_pat': f"%CAR {d['driver_number']} (%"},
                 {'type': 'table'})


_PENALTY = re.compile(r'(?:FIA STEWARDS:\s*)?(?:PENALTY SERVED - )?(?P<what>.+?)\s+FOR CAR \d+ \((?P<code>[A-Z]{3})\)(?:\s*-\s*(?P<why>.+?))?(?:\s*\(\d{1,2}:\d{2}:\d{2}\))?$')


def parse_penalty(message: str) -> tuple[str, str | None]:
    m = _PENALTY.search(message.strip())
    if not m:
        return message, None
    return m.group('what').title(), (m.group('why') or '').title() or None


def explain_penalty_reason(rows, e):
    code = e.code(0)
    if not rows:
        return f'No penalty or steward note for {code} has been issued up to this point of the race.'
    issued = [r for r in rows if r['ruling'] == 'penalty']
    context = [r for r in rows if r['ruling'] in ('investigation', 'noted', 'other', 'lap time deleted')]
    if not issued:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r['ruling']] = counts.get(r['ruling'], 0) + 1
        last = rows[-1]
        mix = ', '.join(f'{n} {k}' for k, n in counts.items())
        return (f"{code} has not been penalised up to this point. The stewards have {len(rows)} note"
                f"{'s' if len(rows) != 1 else ''} on them ({mix}). Most recent (lap {last['lap_number']}, "
                f"{last['ruling']}): {last['message']}.")
    out = []
    for r in issued:
        what, why = parse_penalty(r['message'])
        text = f"{code} received a {what.lower()} on lap {r['lap_number']}"
        text += f" for {why.lower()}." if why else '.'
        earlier = [c for c in context if c['recorded_at'] <= r['recorded_at']]
        if earlier:
            text += f" Earlier steward note (lap {earlier[-1]['lap_number']}): {earlier[-1]['message']}."
        out.append(text)
    served = [r for r in rows if r['ruling'] == 'penalty served']
    if served:
        out.append(f"The penalty has been served (lap {served[-1]['lap_number']}).")
    return ' '.join(out)


def build_penalties_list(e):
    return Built("""SELECT recorded_at, lap_number, message FROM race_control
                    WHERE message ILIKE :pen AND message NOT ILIKE :served ORDER BY recorded_at""",
                 {'pen': '%penalty for car%', 'served': '%penalty served%'}, {'type': 'table'})


def explain_penalties_list(rows, e):
    if not rows:
        return 'No penalties have been issued yet.'
    items = []
    for r in rows[-5:]:
        what, why = parse_penalty(r['message'])
        m = re.search(r'CAR \d+ \(([A-Z]{3})\)', r['message'])
        items.append(f"lap {r['lap_number']}: {m.group(1) if m else '?'} {what.lower()}" + (f" ({why.lower()})" if why else ''))
    return f"{len(rows)} penalt{'ies' if len(rows) != 1 else 'y'} issued so far. Latest: " + '; '.join(items) + '.'


# ---- 20-26. situational ---------------------------------------------------------------------------------------------
def build_weather(e):
    return Built("""SELECT recorded_at, air_temperature, track_temperature, humidity, rainfall, wind_speed
                    FROM weather ORDER BY recorded_at DESC LIMIT 1""", {}, {'type': 'table'})


def explain_weather(rows, e):
    if not rows:
        return 'No weather reading yet.'
    w = rows[0]
    return (f"Air {f(w['air_temperature'], 1)}°C, track {f(w['track_temperature'], 1)}°C, humidity "
            f"{f(w['humidity'], 0)}%, wind {f(w['wind_speed'], 1)} m/s, {'raining' if w['rainfall'] else 'dry'}.")


def build_race_status(e):
    return Built("""SELECT recorded_at, lap_number, category, flag, scope, message FROM race_control
                    WHERE category IN ('Flag', 'SafetyCar', 'SessionStatus') ORDER BY recorded_at DESC LIMIT :limit""",
                 {'limit': e.limit or 8}, {'type': 'table'})


def explain_race_status(rows, e):
    if not rows:
        return 'No flag or safety-car message yet.'
    r = rows[0]
    return f"Latest track message (lap {r['lap_number']}): {r['message']}."


def build_fastest_lap(e):
    return Built("""SELECT RANK() OVER (ORDER BY lap_time_seconds) AS lap_rank, driver_code, driver_name, team_name,
                           lap_number, lap_time_seconds
                    FROM laps WHERE is_valid AND lap_time_seconds IS NOT NULL
                    ORDER BY lap_time_seconds LIMIT :limit""",
                 {'limit': e.limit or 5}, {'type': 'bar', 'x': 'driver_code', 'y': ['lap_time_seconds'], 'title': 'Fastest laps (s)'})


def explain_fastest_lap(rows, e):
    if not rows:
        return EMPTY
    a = rows[0]
    return f"The fastest lap so far is {lap_time(a['lap_time_seconds'])} by {a['driver_code']} on lap {a['lap_number']}."


def build_driver_summary(e):
    return Built("""SELECT cp.driver_code, cp.driver_name, cp.team_name, cp.position, cp.gap_to_leader_seconds AS gap_to_leader,
                           cp.interval_ahead_seconds AS interval_ahead, dp.valid_laps, dp.avg_lap, dp.best_lap, dp.avg_last5,
                           st.compound, COALESCE(st.starting_tyre_age, 0) + st.laps_completed AS tyre_age, st.stint_number
                    FROM current_positions cp
                    LEFT JOIN driver_pace dp ON dp.session_driver_id = cp.session_driver_id
                    LEFT JOIN current_stints st ON st.session_driver_id = cp.session_driver_id
                    WHERE cp.driver_code = :driver""",
                 {'driver': e.code(0)}, {'type': 'table'})


def explain_driver_summary(rows, e):
    if not rows:
        return f'No data for {e.code(0)} yet.'
    r = rows[0]
    out = f"{r['driver_code']} ({r['team_name']})"
    out += f" is P{r['position']}" if r['position'] else ' has no recorded position yet'
    if r['gap_to_leader'] is not None:
        out += f", {f(r['gap_to_leader'], 1)}s behind the leader"
    if r['compound']:
        out += f", on {r['compound'].lower()}s (stint {r['stint_number']}, {r['tyre_age']} laps old)"
    if r['avg_last5'] is not None:
        out += f"; last-five-lap average {f(r['avg_last5'])}s, best lap {lap_time(r['best_lap'])}"
    return out + '.'


def build_gap_between(e):
    return Built("""SELECT driver_code, position, gap_to_leader_seconds AS gap_to_leader, interval_ahead_seconds AS interval_ahead
                    FROM current_positions WHERE driver_code IN (:a, :b) ORDER BY position""",
                 {'a': e.code(0), 'b': e.code(1)}, {'type': 'table'})


def explain_gap_between(rows, e):
    if len(rows) < 2 or any(r['gap_to_leader'] is None and r['position'] != 1 for r in rows):
        return f'The gap between {e.code(0)} and {e.code(1)} is not available yet.'
    a, b = rows[0], rows[1]
    gap = (b['gap_to_leader'] or 0) - (a['gap_to_leader'] or 0)
    return f"{b['driver_code']} (P{b['position']}) is {f(abs(gap), 1)}s behind {a['driver_code']} (P{a['position']})."


def build_recent_events(e):
    return Built("""SELECT rc.recorded_at AS event_time, 'race control' AS kind, rc.message AS detail
                    FROM race_control rc JOIN session_info si ON TRUE
                    WHERE rc.recorded_at >= si.replay_time - (:minutes * INTERVAL '1 minute')
                    UNION ALL
                    SELECT p.pit_exit_at, 'pit stop', p.driver_code || ' left the pits (lap ' || p.lap_number || ')'
                    FROM pit_stops p JOIN session_info si ON TRUE
                    WHERE p.pit_exit_at >= si.replay_time - (:minutes * INTERVAL '1 minute')
                    ORDER BY event_time DESC LIMIT :limit""",
                 {'minutes': e.minutes or 10, 'limit': e.limit or 30}, {'type': 'table'})


def explain_recent_events(rows, e):
    minutes = e.minutes or 10
    if not rows:
        return f'Nothing happened in the last {minutes} minutes of race time.'
    kinds = {}
    for r in rows:
        kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
    return (f"{len(rows)} events in the last {minutes} minutes ("
            + ', '.join(f'{n} {k}' for k, n in kinds.items()) + f"). Latest: {rows[0]['detail']}.")


def build_position_history(e):
    if e.drivers:
        where, params = 'WHERE l.driver_code IN (:d0' + (', :d1' if len(e.drivers) > 1 else '') + ')', \
            {f'd{i}': d['driver_code'] for i, d in enumerate(e.drivers[:2])}
    else:
        where, params = 'JOIN current_positions cp ON cp.session_driver_id = l.session_driver_id WHERE cp.position <= :top', {'top': e.n or 5}
    return Built(f"""SELECT l.driver_code, l.lap_number,
                            (SELECT ps.position FROM positions ps
                              WHERE ps.session_driver_id = l.session_driver_id AND ps.position IS NOT NULL
                                AND ps.recorded_at <= l.lap_end_at ORDER BY ps.recorded_at DESC LIMIT 1) AS position
                     FROM laps l {where} ORDER BY l.lap_number, l.driver_code""",
                 params, {'type': 'position_lines', 'x': 'lap_number', 'series': 'driver_code', 'y': 'position',
                          'title': 'Position by lap'})


def explain_position_history(rows, e):
    if not rows:
        return EMPTY
    codes = sorted({r['driver_code'] for r in rows})
    last = max(r['lap_number'] for r in rows)
    return f"Position by lap for {', '.join(codes)} up to lap {last}."


def build_current_lap(e):
    return Built("""SELECT MAX(lap_number) AS latest_completed_lap, COUNT(DISTINCT driver_code) AS drivers_with_laps,
                           MIN(lap_end_at) AS first_lap_finished_at, MAX(lap_end_at) AS latest_lap_finished_at FROM laps""",
                 {}, {'type': 'table'})


def explain_current_lap(rows, e):
    if not rows or rows[0]['latest_completed_lap'] is None:
        return 'No lap has been completed yet.'
    return f"The leading cars have completed {rows[0]['latest_completed_lap']} laps."


# ---- registry (order = priority: specific before general) -------------------------------------------------------------
W = r'(?:\b)'
INTENTS: list[Intent] = [
    Intent('penalty_reason', 'Why a driver got a penalty',
           ['Why did NOR get a penalty?', 'What was the reason for the VER penalty?', 'Is Hamilton under investigation?'],
           'Filters race-control messages for the driver (matched on the "(CODE)" in the steward text, since OpenF1 leaves '
           'driver_id empty), classifies each message with a CASE expression and orders them by time.',
           [r'(penal|investigat|steward|reprimand|black and white|time penalty|drive.?through|stop.?and.?go|why .* (punish|sanction))'],
           build_penalty_reason, explain_penalty_reason, needs_drivers=1),
    Intent('penalties_list', 'All penalties so far',
           ['Who has been penalised?', 'List the penalties', 'Any penalties so far?'],
           'Selects steward messages announcing a penalty (ILIKE patterns), excluding "penalty served" notices.',
           [r'(who|which|any|all|list|show).*(penal|punish)', r'penalt(y|ies) so far'],
           build_penalties_list, explain_penalties_list),
    Intent('gap_between', 'Gap between two drivers',
           ['What is the gap between VER and NOR?'],
           'Reads both drivers from the current_positions view and subtracts their gaps to the leader.',
           [r'\bgap\b.*\b(between|from|to)\b', r'\bhow far\b'],
           build_gap_between, explain_gap_between, needs_drivers=2),
    Intent('qualifying_vs_race', 'Qualifying versus race performance',
           ['Compare qualifying performance against race performance'],
           "Qualifying sessions are not imported, so this answers with the nearest stored comparison: each driver's first "
           'recorded race position against the current position (ROW_NUMBER CTE joined to current_positions).',
           [r'qualif', r'\bgrid\b'],
           build_positions_gained, explain_qualifying_vs_race,
           note='No qualifying session data is imported (the race results table has no grid positions).'),
    Intent('compare_team_strategies', 'Compare tyre strategies between constructors',
           ['Compare tyre strategies between constructors', 'Compare Ferrari and Mercedes tyre strategy'],
           'Groups tyre stints by team and driver and builds the compound sequence with STRING_AGG ... ORDER BY stint_number.',
           [r'(strateg).*(team|constructor|ferrari|mercedes|mclaren|red bull|williams|alpine|haas|audi|cadillac|sauber|aston|bulls)',
            r'(team|constructor).*(strateg)', r'compare.*(strateg)'],
           build_team_strategies, explain_team_strategies),
    Intent('compare_drivers', 'Compare two drivers',
           ['Compare VER and NOR race pace', 'Compare him with the second-fastest'],
           'Two CTEs of each driver\'s valid laps joined with a FULL JOIN on lap number; the per-lap delta feeds the chart.',
           [r'\b(compare|versus|vs\.?|head.to.head|against|difference between)\b'],
           build_compare, explain_compare, needs_drivers=2),
    Intent('tyre_stints', 'Tyre stints so far',
           ['Show the tyre stints', 'What are the tyre strategies?'],
           'Lists every stint visible at replay time, with the end lap hidden while a stint is still running.',
           [r'(tyre|tire).*(stint|strateg|history)', r'stints?\b'],
           build_tyre_stints, explain_tyre_stints),
    Intent('tyre_degradation', 'Highest tyre degradation',
           ['Who has the highest tyre degradation?'],
           'A CTE of each driver\'s clean laps in the current stint; REGR_SLOPE of lap time against stint lap, ranked with RANK().',
           [r'(degrad|tyre wear|tire wear|tyre drop|falling off|fall.?off)'],
           build_degradation, explain_degradation),
    Intent('undercut', 'Undercut candidates',
           ['Which drivers could benefit from an undercut?'],
           'A self-join of a "current state" CTE (position, gap, tyre age) pairing each car with the one directly ahead.',
           [r'undercut', r'overcut'],
           build_undercut, explain_undercut),
    Intent('overtakes', 'Overtaking opportunities',
           ['Identify potential overtake opportunities', 'Who can overtake?'],
           'Pairs each car with the car ahead and keeps pairs that are close with a clear recent-pace advantage.',
           [r'overtak', r'\bdrs\b', r'(attack|pass).*(opportun|chance)', r'who can (pass|attack)'],
           build_overtakes, explain_overtakes),
    Intent('losing_time', 'Drivers losing significant time',
           ['Identify drivers losing significant time', 'Who is losing pace?'],
           'Window functions give each lap its rolling baseline (previous five laps); latest laps far above it are listed.',
           [r'(losing|lost|lose) (the most |significant |a lot of |much )?(time|pace)', r'losing (time|pace)', r'(slow(ing)?|dropp?ing|fall(ing)? (off|back)).*(pace|time)', r'time lost.*(lap|pace)', r'pace drop'],
           build_losing_time, explain_losing_time),
    Intent('pit_team_avg', 'Fastest average pit stops by team',
           ['Which team has the fastest average pit stops?'],
           'GROUP BY team over stops with a measured stationary time, ranked with RANK().',
           [r'(team|constructor|crew).*(pit|stop)', r'(pit|stop).*(team|constructor|crew)', r'fastest .*pit ?stop'],
           build_pit_team_avg, explain_pit_team_avg, note=PIT_NOTE),
    Intent('not_pitted', 'Drivers who have not pitted',
           ['Which drivers have not pitted yet?'],
           'A NOT EXISTS subquery on pit stops combined with tyre-stint information, because recorded stops are incomplete.',
           [r'(not|haven.?t|hasn.?t|yet to|never).*(pit|stopped)', r'still on (their )?(first|starting|original) (set|tyres?|stint)'],
           build_not_pitted, explain_not_pitted, note=PIT_NOTE),
    Intent('pit_time_lost', 'Time spent in the pits',
           ['Analyse the time lost during pit stops'],
           'SUM and AVG of pit-lane and stationary times per driver, ordered with NULLS LAST.',
           [r'(time|seconds).*(lost|spent).*(pit)', r'pit.*(time lost|loss)', r'time lost.*pit'],
           build_pit_time_lost, explain_pit_time_lost, note=PIT_NOTE),
    Intent('pit_counts', 'Pit stops per driver',
           ['How many pit stops has each driver completed?'],
           'LEFT JOINs drivers to recorded pit stops and to tyre stints; stops are counted both ways because records are incomplete.',
           [r'how many (pit|stops)', r'pit ?stops? (count|so far|completed|made)', r'(number of|count of) (pit|stops)'],
           build_pit_counts, explain_pit_counts, note=PIT_NOTE),
    Intent('tyres_now', 'Current tyres',
           ['Which drivers are currently running on hard tyres?', 'Who is on softs?'],
           'Joins each driver\'s current stint with their position and computes tyre age from laps completed.',
           [r'\b(soft|medium|hard|inter(mediate)?s?|wet)s?\b.*(tyre|tire|compound|running|on)', r'(on|running).*\b(soft|medium|hard|inter|wet)',
            r'(current|which|what).*(tyre|tire|compound)'],
           build_tyres_now, explain_tyres_now),
    Intent('positions_gained', 'Positions gained or lost',
           ['Who gained the most positions?', 'Who lost the most places?'],
           'A ROW_NUMBER CTE finds each driver\'s first recorded position; it is joined to the current position.',
           [r'(gain|lost|lose|dropp?ed|made up|biggest mover|moved up|climb)', r'positions? (gained|lost)'],
           build_positions_gained, explain_positions_gained,
           note='No qualifying or grid data is stored, so the baseline is each driver\'s first recorded race position.'),
    Intent('consistency', 'Most consistent driver',
           ['Which driver has been most consistent?'],
           'STDDEV_SAMP of each driver\'s clean lap times, ranked ascending; HAVING requires at least five laps.',
           [r'consisten', r'(smoothest|steadiest|least variation|lap.time (spread|variation))'],
           build_consistency, explain_consistency),
    Intent('recent_pace', 'Pace over the last N laps',
           ['Which driver has the strongest race pace over the last five laps?'],
           'ROW_NUMBER() ranks each driver\'s laps by recency; AVG over recency <= N with HAVING, ranked with RANK().',
           [r'(last|past|recent|previous|final)\s+\w+\s+(clean\s+)?laps', r'\brecent pace\b', r'pace (over|in) the last'],
           build_recent_pace, explain_recent_pace),
    Intent('fastest_avg', 'Fastest average pace',
           ['Who currently has the fastest average lap time?', 'Who has the best race pace?'],
           'A CTE keeps clean laps (valid and within 107% of the driver\'s best, via a window MIN); AVG per driver, RANK().',
           [r'(fastest|quickest|best|strongest).*(average|avg|pace|race pace)', r'average (lap|pace)', r'(who|which).*(fastest|quickest)\b(?!.*\blap\b)'],
           build_fastest_avg, explain_fastest_avg),
    Intent('fastest_lap', 'Fastest lap',
           ['What is the fastest lap so far?'],
           'The quickest valid laps so far, ranked with RANK().',
           [r'fastest lap', r'quickest lap', r'best lap'],
           build_fastest_lap, explain_fastest_lap),
    Intent('position_history', 'Position progression',
           ['Show the position progression', 'How has VER moved through the race?'],
           'For each completed lap, a correlated subquery finds the last position recorded at or before that lap\'s end.',
           [r'(position|places?).*(progress|history|over time|by lap|through the race|changes)', r'progression', r'how has .* moved'],
           build_position_history, explain_position_history),
    Intent('recent_events', 'What just happened',
           ['What happened in the last 10 minutes?'],
           'UNION ALL of race-control messages and pit exits, filtered with a time window relative to the replay clock.',
           [r'(last|past|previous)\s+\w+\s+minutes?', r'what (just )?happened', r'recent (events|news|messages)'],
           build_recent_events, explain_recent_events),
    Intent('weather', 'Weather',
           ['What is the weather like?'],
           'The latest weather sample at replay time.',
           [r'weather', r'\b(rain|raining|temperature|wind|humid)'],
           build_weather, explain_weather),
    Intent('race_status', 'Race status and flags',
           ['What is the race status?', 'Is there a safety car?'],
           'The latest flag, safety-car and session-status messages from race control.',
           [r'(race|track) status', r'safety car', r'\b(vsc|yellow flag|red flag|flags?)\b', r'what.s going on'],
           build_race_status, explain_race_status),
    Intent('current_lap', 'Current lap',
           ['What lap is it?'],
           'MAX lap number among completed laps at replay time.',
           [r'what lap', r'which lap', r'current lap', r'how many laps'],
           build_current_lap, explain_current_lap),
    Intent('driver_summary', 'Driver summary',
           ['How is VER doing?', 'Tell me about Norris'],
           'Joins position, pace and current-stint views for one driver.',
           [r'(how is|how.s|tell me about|status of|summary of)'],
           build_driver_summary, explain_driver_summary, needs_drivers=1),
    Intent('standings', 'Race order',
           ['Who is leading?', 'Show the standings'],
           'The current_positions view (latest recorded position and gap per driver).',
           [r'(standings?|running order|race order|classification|leaderboard|who(\s+is|.?s)?\s+(leading|winning|in the lead|first|in front|ahead)|who leads|the leader|top \w+)',
            r'(current )?positions?'],
           build_standings, explain_standings),
]

INTENT_BY_NAME = {i.name: i for i in INTENTS}


def suggestions(k: int = 8) -> list[str]:
    return [ex for i in INTENTS for ex in i.examples[:1]][:k]
