"""Compatibility shim: `backend.main:app` is the same app as `backend/main.py`.

There used to be two diverging copies of the API here (this one was stale and read `.env` from the
wrong folder). The single source of truth is `backend/main.py`; run the server from the `backend/`
folder with either `uvicorn main:app` or `uvicorn backend.main:app`.
"""
from main import *  # noqa: F401,F403  (re-exports `app`, `get_connection`, `query_db`, ...)
from main import app  # noqa: F401
