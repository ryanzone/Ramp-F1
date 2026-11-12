"""Replay HTTP, SSE and WebSocket endpoints.

Every endpoint takes an optional `replay_id`. Without one it uses the offline demo
snapshot replay (the original behaviour); with one it uses that user's own replay
created by POST /api/replay/start, so clocks never leak between users.

All handlers are `async def` on purpose: ReplayState is only touched on the event
loop, which makes each control/tick atomic without locks.
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StrictFloat, StrictInt, model_validator

from backend import replay, replay_analytics as analytics
from backend.replay_clock import MAX_SPEED, MIN_SPEED
from backend.replay_service import ReplayNotReady, get_service, list_sessions

router = APIRouter(prefix='/api/replay', tags=['replay'])
ws_router = APIRouter(tags=['replay'])

ALLOWED_ORIGINS = {'http://localhost:5173', 'http://127.0.0.1:5173',
                   *(o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip())}
KEEPALIVE_SECONDS = 15


async def entry_for(replay_id: str | None):
    try:
        return await get_service().resolve(replay_id)
    except KeyError:
        raise HTTPException(404, 'Unknown replay_id; start one with POST /api/replay/start')
    except FileNotFoundError:
        raise HTTPException(503, 'No saved demo session available; start a database replay instead')


# ---- request bodies ----------------------------------------------------------------
class StartBody(BaseModel):
    session_id: int
    speed: StrictInt | StrictFloat = Field(1.0, description=f'{MIN_SPEED} to {MAX_SPEED}')
    autoplay: bool = False


class SeekBody(BaseModel):
    t: str | None = Field(None, description='ISO-8601 time with timezone')
    offset_seconds: StrictInt | StrictFloat | None = Field(None, description='Seconds from replay start')

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.t is None) == (self.offset_seconds is None):
            raise ValueError('provide exactly one of t or offset_seconds')
        return self


class SpeedBody(BaseModel):
    speed: StrictInt | StrictFloat = Field(description=f'{MIN_SPEED} to {MAX_SPEED}')


def run_control(entry, action: str, **params) -> dict:
    try:
        return get_service().control(entry, action, **params)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def seek_params(body: SeekBody) -> dict:
    if body.t is None:
        return {'offset_seconds': body.offset_seconds}
    t = replay.parse_time(body.t)
    if t is None:
        raise HTTPException(422, 't must be an ISO-8601 time with a timezone')
    return {'t': t}


# ---- HTTP ---------------------------------------------------------------------------
@router.get('/sessions')
async def sessions():
    try:
        return await asyncio.to_thread(list_sessions)
    except Exception as exc:
        raise HTTPException(503, f'Database unavailable or replay migration missing: {exc}')


@router.post('/start')
async def start(body: StartBody):
    service = get_service()
    try:
        entry = await service.create(body.session_id, speed=float(body.speed))
    except LookupError:
        raise HTTPException(404, f'Unknown session {body.session_id}')
    except ReplayNotReady as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if body.autoplay:
        service.control(entry, 'play')
    return {'replay_id': entry.state.id, 'state': entry.state.state_dict()}


@router.get('/state')
async def get_state(replay_id: str | None = Query(None)):
    entry = await entry_for(replay_id)
    return run_control_state(entry)


def run_control_state(entry) -> dict:
    """Current state after settling elapsed time (publishes any events that became due)."""
    service = get_service()
    service._tick(entry)
    return entry.state.state_dict()


@router.post('/play')
async def post_play(replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'play')


@router.post('/resume')
async def post_resume(replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'resume')


@router.post('/pause')
async def post_pause(replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'pause')


@router.post('/reset')
async def post_reset(replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'reset')


@router.post('/speed')
async def post_speed(body: SpeedBody, replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'speed', speed=body.speed)


@router.post('/seek')
async def post_seek(body: SeekBody, replay_id: str | None = Query(None)):
    return run_control(await entry_for(replay_id), 'seek', **seek_params(body))


@router.delete('/{replay_id}')
async def delete_replay(replay_id: str):
    if not get_service().stop(replay_id):
        raise HTTPException(404, 'Unknown replay_id')
    return {'stopped': replay_id}


@router.get('/analytics')
async def get_analytics(replay_id: str | None = Query(None)):
    """Python rule-based pace/pit anomalies from released events only (see REPLAY_LEAKS.md)."""
    entry = await entry_for(replay_id)
    run_control_state(entry)
    return analytics.analyse(entry.state.clock.seen(), entry.state.clock.now)


# ---- SSE -----------------------------------------------------------------------------
def sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, allow_nan=False)}\n\n'


def sse_payload(message: dict) -> tuple[str, dict]:
    """Keep the original SSE shapes: `state` carries the state dict itself."""
    kind = message['type']
    if kind == 'state':
        return 'state', message['state']
    return kind, {k: v for k, v in message.items() if k != 'type'}


async def sse_stream(entry, keepalive: float = KEEPALIVE_SECONDS):
    service = get_service()
    sub = service.hub.subscribe(entry.state.id, first_message=entry.state.reset_message())
    try:
        while True:
            try:
                message = await asyncio.wait_for(sub.queue.get(), keepalive)
            except asyncio.TimeoutError:
                yield ': keepalive\n\n'
                continue
            yield sse(*sse_payload(message))
    finally:
        service.hub.unsubscribe(entry.state.id, sub)


@router.get('/stream')
async def stream(replay_id: str | None = Query(None)):
    entry = await entry_for(replay_id)
    return StreamingResponse(sse_stream(entry), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ---- WebSocket ---------------------------------------------------------------------------
@ws_router.websocket('/ws/replay')
async def ws_replay(ws: WebSocket, replay_id: str | None = None):
    """Server pushes {type: reset|events|state|error}. Client sends
    {"action": "play"|"resume"|"pause"|"reset"|"seek"|"speed", ...params}."""
    origin = ws.headers.get('origin')
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await ws.close(code=1008)
        return
    try:
        entry = await get_service().resolve(replay_id)
    except (KeyError, FileNotFoundError):
        await ws.close(code=4404)
        return
    await ws.accept()
    service = get_service()
    sub = service.hub.subscribe(entry.state.id, first_message=entry.state.reset_message())

    async def pump():
        while True:
            await ws.send_json(await sub.queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            request = await ws.receive_json()
            try:
                action = request.get('action')
                params = {}
                if action == 'seek':
                    if request.get('t') is not None:
                        t = replay.parse_time(request['t'])
                        if t is None:
                            raise ValueError('t must be an ISO-8601 time with a timezone')
                        params['t'] = t
                    else:
                        params['offset_seconds'] = request.get('offset_seconds')
                elif action == 'speed':
                    params['speed'] = request.get('speed')
                service.control(entry, action, **params)
            except ValueError as exc:
                sub.push({'type': 'error', 'message': str(exc)})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        service.hub.unsubscribe(entry.state.id, sub)
