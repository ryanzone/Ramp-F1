"""Analytics endpoints: natural-language questions answered by real SQL at the replay time."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from backend.analytics_service import AnalyticsUnavailable, get_analytics
from backend.intent_parser import MAX_QUESTION_LENGTH
from backend.query_executor import ExecutorUnavailable, QueryError, QueryTimeout
from backend.replay_routes import ALLOWED_ORIGINS

router = APIRouter(prefix='/api/analytics', tags=['analytics'])
ws_router = APIRouter(tags=['analytics'])


class QueryBody(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    replay_id: str | None = None
    remember: bool = True        # False for background chart refreshes: no history, no follow-up context


class ExplainBody(BaseModel):
    query_id: str
    replay_id: str | None = None


async def run_question(replay_id, question, on_stage=None, remember=True) -> dict:
    try:
        return await get_analytics().ask(replay_id, question, on_stage, remember)
    except KeyError:
        raise HTTPException(404, 'Unknown replay_id; start one with POST /api/replay/start')
    except AnalyticsUnavailable as exc:
        raise HTTPException(409, str(exc))
    except QueryTimeout as exc:
        raise HTTPException(504, str(exc))
    except ExecutorUnavailable as exc:
        raise HTTPException(503, f'Analytics database unavailable: {exc}')
    except QueryError as exc:
        raise HTTPException(500, f'Query failed: {exc}')


@router.post('/query')
async def query(body: QueryBody):
    return await run_question(body.replay_id, body.question, remember=body.remember)


@router.post('/explain')
async def explain(body: ExplainBody):
    replay_key = body.replay_id
    if replay_key is None:
        raise HTTPException(422, 'replay_id is required')
    found = get_analytics().explain(replay_key, body.query_id)
    if found is None:
        raise HTTPException(404, 'Unknown query_id for this replay')
    return found


@router.get('/history')
async def history(replay_id: str = Query(...)):
    return get_analytics().history(replay_id)


@router.get('/intents')
async def intents():
    return get_analytics().intents()


@ws_router.websocket('/ws/analytics')
async def ws_analytics(ws: WebSocket):
    """Client sends {"question": "...", "replay_id": "..."}; server streams
    {type: status, stage} then {type: result, result} or {type: error, status, message}."""
    origin = ws.headers.get('origin')
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            request = await ws.receive_json()
            question, replay_id = request.get('question'), request.get('replay_id')
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_LENGTH:
                await ws.send_json({'type': 'error', 'status': 422, 'message': 'question must be 1-500 characters'})
                continue
            stages: list[str] = []
            try:
                result = await run_question(replay_id, question, stages.append)
                for s in stages:
                    await ws.send_json({'type': 'status', 'stage': s})
                await ws.send_json({'type': 'result', 'result': result})
            except HTTPException as exc:
                await ws.send_json({'type': 'error', 'status': exc.status_code, 'message': exc.detail})
    except (WebSocketDisconnect, RuntimeError):
        pass
