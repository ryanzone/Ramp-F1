"""Time-aware SQL analytics service: question -> SQL -> validated -> executed -> explained.

For one replay it keeps the follow-up context and a history of answers. Results are cached
per (query, parameters, session, replay time), so any change of the replay clock misses
the cache automatically: an answer can never be reused at a different moment.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime

import sqlglot

from backend.intent_parser import Context, Parsed, parse, subject_from_rows
from backend.query_executor import ExecutorUnavailable, QueryExecutor, QueryResult, QueryTimeout
from backend.sql_generator import INTENTS, suggestions
from backend.sql_validator import SqlValidationError, Validated, validate

HISTORY_PER_REPLAY = 50
HISTORY_ROWS = 100
CACHE_SIZE = 256
MAX_CONTEXTS = 200

ROSTER_SQL = 'SELECT driver_number, driver_code, driver_name, team_name FROM drivers ORDER BY driver_number'


class AnalyticsUnavailable(RuntimeError):
    """This replay is not backed by the database (e.g. the offline demo snapshot)."""


def pretty_sql(sql: str) -> str:
    try:
        text = sqlglot.parse_one(sql, read='postgres').sql(dialect='postgres', pretty=True, comments=False)
    except Exception:
        text = sql
    return re.sub(r'%\(([a-z_][a-z0-9_]*)\)s', r':\1', text)       # show readable :name placeholders


def describe_features(features: dict) -> list[str]:
    labels = [('ctes', 'CTE (WITH)'), ('joins', 'JOIN'), ('window_functions', 'window function'),
              ('subqueries', 'subquery'), ('aggregates', 'aggregate'), ('case_expressions', 'CASE expression'),
              ('set_operations', 'set operation (UNION)')]
    out = [f"{features[k]} {label}{'s' if features[k] != 1 else ''}" for k, label in labels if features.get(k)]
    if features.get('group_by'):
        out.append('GROUP BY')
    if features.get('having'):
        out.append('HAVING')
    return out or ['filtering and ordering on a single time-bounded view']


class AnalyticsService:
    def __init__(self, replays, executor: QueryExecutor | None = None):
        self._replays = replays                       # callable returning the ReplayService
        self.executor = executor or QueryExecutor()
        self._contexts: OrderedDict[str, Context] = OrderedDict()
        self._history: dict[str, list[dict]] = {}
        self._cache: OrderedDict[tuple, QueryResult] = OrderedDict()
        self._rosters: dict[int, list[dict]] = {}
        self._validated: dict[str, Validated] = {}

    # ---- helpers -------------------------------------------------------------------------
    def _context(self, replay_id: str) -> Context:
        ctx = self._contexts.setdefault(replay_id, Context())
        self._contexts.move_to_end(replay_id)
        while len(self._contexts) > MAX_CONTEXTS:
            old, _ = self._contexts.popitem(last=False)
            self._history.pop(old, None)
        return ctx

    async def _run(self, query: Validated, params: dict, session_id: int, at: datetime) -> tuple[QueryResult, bool]:
        key = (query.sql, json.dumps(params, sort_keys=True, default=str), session_id, at.isoformat())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key], True
        result = await asyncio.to_thread(self.executor.run, query, params, session_id, at)
        self._cache[key] = result
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return result, False

    async def _roster(self, session_id: int, at: datetime) -> list[dict]:
        if session_id not in self._rosters:
            catalog = await asyncio.to_thread(self.executor.catalog)
            result = await asyncio.to_thread(self.executor.run, validate(ROSTER_SQL, catalog), {}, session_id, at)
            self._rosters[session_id] = result.as_dicts()
        return self._rosters[session_id]

    # ---- ask --------------------------------------------------------------------------------
    async def ask(self, replay_id: str | None, question: str, on_stage=None, remember: bool = True) -> dict:
        stage = on_stage or (lambda name: None)
        service = self._replays()
        entry = await service.resolve(replay_id)
        meta = entry.state.timeline.meta
        session_id = meta.get('db_session_id')
        if session_id is None:
            raise AnalyticsUnavailable('SQL analytics needs a database replay: start one with POST /api/replay/start')
        service.sync(entry)
        at = entry.state.clock.now
        replay_key = entry.state.id
        ctx = self._context(replay_key)

        stage('parsing')
        roster = await self._roster(session_id, at)
        parsed: Parsed = parse(question, roster, ctx)
        base = {'id': secrets.token_hex(8), 'question': question, 'replay_id': replay_key,
                'replay_time': at.isoformat(), 'current_lap': entry.state.current_lap,
                'time_boundary': f'Only data with timestamps up to {at.isoformat()} is visible to this query.',
                'used_context': parsed.used_context, 'asked_at': datetime.now().astimezone().isoformat()}

        if parsed.intent is None or parsed.clarification:
            status = 'needs_clarification' if parsed.clarification else 'unsupported'
            answer = parsed.clarification or (parsed.message + ' Try asking: ' + ' | '.join(suggestions(5)))
            result = {**base, 'status': status, 'intent': parsed.intent.name if parsed.intent else None,
                      'answer': answer, 'sql': None, 'params': {}, 'columns': [], 'rows': [], 'row_count': 0,
                      'elapsed_ms': 0, 'cached': False, 'chart': None, 'suggestions': suggestions(8)}
            if remember:
                self._remember(replay_key, result)
            stage('done')
            return result

        intent, entities = parsed.intent, parsed.entities
        built = intent.build(entities)
        stage('validating')
        catalog = await asyncio.to_thread(self.executor.catalog)
        try:
            query = validate(built.sql, catalog, set(built.params))
        except SqlValidationError as exc:             # a template bug, never user input
            raise RuntimeError(f'internal template error in {intent.name}: {exc}') from None
        stage('executing')
        started = time.perf_counter()
        qr, cached = await self._run(query, built.params, session_id, at)
        rows = qr.as_dicts()
        stage('explaining')
        answer = intent.explain(rows, entities)
        if qr.truncated:
            answer += f' (Showing the first {len(rows)} rows.)'
        result = {**base, 'status': 'ok', 'intent': intent.name, 'title': intent.title, 'answer': answer,
                  'note': intent.note, 'sql': pretty_sql(built.sql), 'params': built.params,
                  'columns': qr.columns, 'rows': qr.rows, 'row_count': len(qr.rows), 'truncated': qr.truncated,
                  'elapsed_ms': qr.elapsed_ms if not cached else round((time.perf_counter() - started) * 1000, 1),
                  'cached': cached, 'chart': built.chart, 'features': describe_features(query.features),
                  'tables': sorted(query.tables), 'how': intent.how}
        if remember:                                  # background chart queries must not change the conversation
            self._validated[result['id']] = query
            subject = subject_from_rows(rows) or (entities.drivers[0]['driver_code'] if entities.drivers else None)
            ctx.last_intent, ctx.last_rows = intent.name, rows
            ctx.subject = next((d for d in roster if d['driver_code'] == subject), ctx.subject)
            self._remember(replay_key, result)
        stage('done')
        return result

    def _remember(self, replay_id: str, result: dict) -> None:
        item = {k: v for k, v in result.items() if k not in ('rows', 'suggestions')}
        item['rows'] = result['rows'][:HISTORY_ROWS]
        history = self._history.setdefault(replay_id, [])
        history.append(item)
        del history[:-HISTORY_PER_REPLAY]

    # ---- post-race dashboard (isolated from live chart/question intents) -------------------------
    async def postrace_analysis(self, replay_id: str | None) -> dict:
        service = self._replays()
        entry = await service.resolve(replay_id)
        service.sync(entry)
        if not entry.state.clock.finished:
            raise ValueError('Post-race analysis is available only after the replay has finished.')
        session_id = entry.state.timeline.meta.get('db_session_id')
        if session_id is None:
            raise AnalyticsUnavailable('Post-race SQL analysis requires a database-backed replay.')

        # The replay clock is at the end of the timeline, so these replay.* views expose
        # the complete race while preserving the same session/time isolation as Pit Wall.
        at = entry.state.clock.now
        catalog = await asyncio.to_thread(self.executor.catalog)
        definitions = {
            'pace': (
                """WITH base AS (
                       SELECT d.driver_code, d.driver_name, d.team_name,
                              l.lap_number, l.lap_time_seconds
                       FROM laps l
                       JOIN drivers d ON d.session_driver_id = l.session_driver_id
                       WHERE l.is_valid AND l.lap_time_seconds IS NOT NULL
                   ), best AS (
                       SELECT *, MIN(lap_time_seconds) OVER (PARTITION BY driver_code) AS best_lap
                       FROM base
                   ), clean AS (
                       SELECT * FROM best WHERE lap_time_seconds <= best_lap * 1.07
                   )
                   SELECT driver_code, driver_name, team_name,
                          COUNT(*) AS laps_used,
                          ROUND(AVG(lap_time_seconds)::numeric, 3) AS avg_lap
                   FROM clean
                   GROUP BY driver_code, driver_name, team_name
                   ORDER BY avg_lap, driver_code""",
                {'type': 'bar', 'x': 'driver_code', 'y': ['avg_lap'], 'title': 'Average clean lap (s)'},
            ),
            'positions': (
                """SELECT d.driver_code, l.lap_number,
                          (SELECT p.position FROM positions p
                           WHERE p.session_driver_id = l.session_driver_id
                             AND p.position IS NOT NULL
                             AND p.recorded_at <= l.lap_end_at
                           ORDER BY p.recorded_at DESC LIMIT 1) AS position
                   FROM laps l
                   JOIN drivers d ON d.session_driver_id = l.session_driver_id
                   WHERE l.lap_end_at IS NOT NULL
                   ORDER BY l.lap_number, d.driver_code""",
                {'type': 'position_lines', 'x': 'lap_number', 'series': 'driver_code', 'y': 'position',
                 'title': 'Position by lap — full grid'},
            ),
            'stints': (
                """SELECT d.driver_code, d.team_name, ts.stint_number, ts.compound, ts.start_lap,
                          COALESCE(
                              ts.end_lap,
                              (SELECT MAX(l.lap_number) FROM laps l
                               WHERE l.session_driver_id = ts.session_driver_id)
                          ) AS last_lap,
                          CASE WHEN ts.end_lap IS NULL THEN 'open at race end' ELSE 'finished' END AS status,
                          GREATEST(
                              COALESCE(
                                  ts.end_lap,
                                  (SELECT MAX(l.lap_number) FROM laps l
                                   WHERE l.session_driver_id = ts.session_driver_id)
                              ) - ts.start_lap + 1,
                              0
                          ) AS laps_completed
                   FROM tyre_stints ts
                   JOIN drivers d ON d.session_driver_id = ts.session_driver_id
                   ORDER BY d.team_name, d.driver_code, ts.stint_number""",
                {'type': 'tyre_stints', 'title': 'Tyre stints — full grid'},
            ),
                    }
        output = {}
        for key, (sql, chart) in definitions.items():
            query = validate(sql, catalog)
            result = await asyncio.to_thread(self.executor.run, query, {}, session_id, at, row_limit=5000)
            output[key] = {
                'status': 'ok', 'title': chart.get('title'),
                'answer': f"{len(result.rows)} rows returned.",
                'columns': result.columns, 'rows': result.rows,
                'row_count': len(result.rows), 'truncated': result.truncated,
                'chart': chart, 'sql': pretty_sql(sql), 'elapsed_ms': result.elapsed_ms,
            }
        return {'replay_id': entry.state.id, 'current_lap': entry.state.current_lap,
                'total_laps': entry.state.total_laps, 'charts': output}

    # ---- history / explain / intents -------------------------------------------------------------
    def history(self, replay_id: str) -> list[dict]:
        return [{k: v for k, v in h.items() if k != 'rows'} for h in reversed(self._history.get(replay_id, []))]

    def explain(self, replay_id: str, query_id: str) -> dict | None:
        for h in self._history.get(replay_id, []):
            if h['id'] == query_id:
                return {'id': h['id'], 'question': h['question'], 'intent': h['intent'], 'status': h['status'],
                        'how': h.get('how'), 'sql': h.get('sql'), 'params': h.get('params'),
                        'techniques': h.get('features', []), 'tables': h.get('tables', []),
                        'time_boundary': h['time_boundary'], 'replay_time': h['replay_time'],
                        'note': h.get('note'),
                        'safety': ['single SELECT validated on the syntax tree', 'only replay.* views are readable',
                                   'values are bound parameters', 'read-only transaction with a timeout and row limit',
                                   'the database hides every row after the replay time']}
        return None

    @staticmethod
    def intents() -> list[dict]:
        return [{'name': i.name, 'title': i.title, 'examples': i.examples, 'note': i.note,
                 'needs_drivers': i.needs_drivers} for i in INTENTS]


_service: AnalyticsService | None = None


def get_analytics() -> AnalyticsService:
    global _service
    if _service is None:
        from backend.replay_service import get_service
        _service = AnalyticsService(get_service)
    return _service


def set_analytics(service: AnalyticsService | None) -> None:
    global _service
    _service = service
