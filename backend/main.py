
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

app = FastAPI(title="F1 Strategy Analysis API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "f1_analytics"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


def query_db(sql, params=()):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {exc}",
        ) from exc


@app.get("/")
def home():
    return {"message": "F1 Strategy Analysis API is running"}


@app.get("/api/health")
def health():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() AS database")
                result = cur.fetchone()
        return {"status": "ok", "database": result["database"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/races")
def races():
    return query_db("""
        SELECT r.race_id, r.season, r.round_number, r.race_name,
               r.race_date, c.circuit_name, c.country,
               s.session_id
        FROM races r
        JOIN circuits c ON c.circuit_id = r.circuit_id
        JOIN sessions s ON s.race_id = r.race_id
        ORDER BY r.season DESC, r.round_number
    """)


@app.get("/api/drivers")
def drivers(session_id: int | None = None):
    return query_db("""
        SELECT DISTINCT d.driver_id, d.driver_number,
               d.driver_code, d.driver_name, t.team_name
        FROM drivers d
        JOIN session_drivers sd ON sd.driver_id = d.driver_id
        JOIN teams t ON t.team_id = sd.team_id
        WHERE (%s IS NULL OR sd.session_id = %s)
        ORDER BY d.driver_number
    """, (session_id, session_id))


@app.get("/api/laps")
def laps(
    driver_code: str | None = None,
    session_id: int | None = None,
    limit: int = Query(default=5000, ge=1, le=10000),
):
    if driver_code is None:
        return query_db("""
            SELECT d.driver_code, d.driver_name, l.lap_number,
                   l.lap_time_seconds, l.sector1_seconds,
                   l.sector2_seconds, l.sector3_seconds,
                   l.speed_trap_kmh
            FROM laps l
            JOIN session_drivers sd
              ON sd.session_driver_id = l.session_driver_id
            JOIN drivers d ON d.driver_id = sd.driver_id
            WHERE (%s IS NULL OR sd.session_id = %s)
            ORDER BY l.lap_number, d.driver_code
            LIMIT %s
        """, (session_id, session_id, limit))
    return query_db("""
        SELECT d.driver_code, d.driver_name, l.lap_number,
               l.lap_time_seconds, l.sector1_seconds,
               l.sector2_seconds, l.sector3_seconds,
               l.speed_trap_kmh
        FROM laps l
        JOIN session_drivers sd
          ON sd.session_driver_id = l.session_driver_id
        JOIN drivers d ON d.driver_id = sd.driver_id
        WHERE d.driver_code = %s
          AND (%s IS NULL OR sd.session_id = %s)
        ORDER BY l.lap_number, d.driver_code
        LIMIT %s
    """, (driver_code, session_id, session_id, limit))


@app.get("/api/pit-stops")
def pit_stops(session_id: int | None = None):
    return query_db("""
        SELECT d.driver_code, p.lap_number, p.stop_number,
               p.lane_duration_seconds, p.stop_duration_seconds,
               p.pit_timestamp
        FROM pit_stops p
        JOIN session_drivers sd
          ON sd.session_driver_id = p.session_driver_id
        JOIN drivers d ON d.driver_id = sd.driver_id
        WHERE (%s IS NULL OR sd.session_id = %s)
        ORDER BY p.lap_number, d.driver_code
    """, (session_id, session_id))


@app.get("/api/tyre-stints")
def tyre_stints(session_id: int | None = None):
    return query_db("""
        SELECT d.driver_code, ts.stint_number, ts.compound,
               ts.start_lap, ts.end_lap, ts.starting_tyre_age
        FROM tyre_stints ts
        JOIN session_drivers sd
          ON sd.session_driver_id = ts.session_driver_id
        JOIN drivers d ON d.driver_id = sd.driver_id
        WHERE (%s IS NULL OR sd.session_id = %s)
        ORDER BY d.driver_code, ts.stint_number
    """, (session_id, session_id))


@app.get("/api/weather")
def weather(session_id: int | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return query_db("""
        SELECT recorded_at, air_temperature, track_temperature,
               humidity, rainfall, wind_speed
        FROM weather_samples
        WHERE (%s IS NULL OR session_id = %s)
        ORDER BY recorded_at
        LIMIT %s
    """, (session_id, session_id, limit))


@app.get("/api/race-control")
def race_control(session_id: int | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    return query_db("""
        SELECT d.driver_code, rc.recorded_at, rc.lap_number,
               rc.category, rc.flag, rc.scope, rc.message
        FROM race_control_events rc
        LEFT JOIN drivers d ON d.driver_id = rc.driver_id
        WHERE (%s IS NULL OR rc.session_id = %s)
        ORDER BY rc.recorded_at
        LIMIT %s
    """, (session_id, session_id, limit))
