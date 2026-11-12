"""Apply (or undo) queries/13_replay_time_aware.sql using the admin DB credentials in .env.

    python backend/apply_replay_sql.py             apply
    python backend/apply_replay_sql.py --dry-run   apply inside a transaction, print checks, ROLL BACK
    python backend/apply_replay_sql.py --down      undo

Required in .env (secrets never live in code or SQL files):
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD   admin connection (as import_f1.py)
    RAMP_RO_PASSWORD     password for the read-only role `ramp_readonly`
    REPLAY_CLOCK_SECRET  secret that lets the backend move a connection's replay clock
Generate values with:  python -c "import secrets; print(secrets.token_urlsafe(32))"
"""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

HERE = Path(__file__).resolve().parent.parent / "queries"
load_dotenv(HERE.parent / ".env")


def connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "f1_analytics"), user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"))


def render(conn, script: str) -> str:
    missing = [k for k in ("RAMP_RO_PASSWORD", "REPLAY_CLOCK_SECRET") if not os.getenv(k)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in .env first (see the docstring of this file).")
    return (script
            .replace("{{RO_PASSWORD}}", sql.Literal(os.environ["RAMP_RO_PASSWORD"]).as_string(conn))
            .replace("{{CLOCK_SECRET}}", sql.Literal(os.environ["REPLAY_CLOCK_SECRET"]).as_string(conn)))


def checks(conn):
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='laps' "
                "AND column_name IN ('lap_start_at','lap_end_at') ORDER BY 1")
    print("laps columns:", [r[0] for r in cur.fetchall()])
    cur.execute("SELECT table_name FROM information_schema.views WHERE table_schema='replay' ORDER BY 1")
    print("replay views:", [r[0] for r in cur.fetchall()])
    cur.execute("SELECT rolname FROM pg_roles WHERE rolname='ramp_readonly'")
    print("read-only role:", cur.fetchone())


def main():
    down = "--down" in sys.argv
    dry = "--dry-run" in sys.argv
    name = "14_replay_time_aware_undo.sql" if down else "13_replay_time_aware.sql"
    with connect() as conn:
        script = (HERE / name).read_text(encoding="utf-8")
        conn.execute(script if down else render(conn, script))   # no params: multi-statement is fine
        if dry:
            checks(conn)
            conn.rollback()
            print("Dry run complete: everything rolled back, nothing was changed.")
        else:
            conn.commit()
            print(("Undone: " if down else "Applied: ") + name)


if __name__ == "__main__":
    main()
