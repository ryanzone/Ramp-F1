
import os
import requests
import psycopg
from dotenv import load_dotenv

load_dotenv()

API = "https://api.openf1.org/v1"
YEAR = 2025
RACE_COUNTRY = "United Arab Emirates"


def fetch(endpoint, **params):
    response = requests.get(
        f"{API}/{endpoint}",
        params=params,
        timeout=60
    )
    response.raise_for_status()
    return response.json()


def main():
    # Find the 2025 Abu Dhabi race session
    sessions = fetch("sessions", year=YEAR)

    race_sessions = [
        s for s in sessions
        if s.get("session_type") == "Race"
        and s.get("country_name") == RACE_COUNTRY
    ]

    if not race_sessions:
        raise RuntimeError(
            "Race session not found. Check the API session list."
        )

    session = race_sessions[0]
    session_key = session["session_key"]

    print("Race:", session.get("session_name"))
    print("Circuit:", session.get("circuit_short_name"))
    print("Session key:", session_key)

    # Fetch driver and lap data before opening a transaction
    drivers_data = fetch("drivers", session_key=session_key)
    laps_data = fetch("laps", session_key=session_key)

    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("DB_NAME", "f1_analytics"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD"),
    }

    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:

            # 1. CIRCUITS
            circuit_name = session.get("circuit_short_name") or "Unknown"

            cur.execute(
                """
                SELECT circuit_id FROM circuits
                WHERE circuit_name = %s
                """,
                (circuit_name,)
            )
            row = cur.fetchone()

            if row:
                circuit_id = row[0]
            else:
                cur.execute(
                    """
                    INSERT INTO circuits
                        (circuit_name, country, circuit_location)
                    VALUES (%s, %s, %s)
                    RETURNING circuit_id
                    """,
                    (
                        circuit_name,
                        session.get("country_name"),
                        session.get("location"),
                    )
                )
                circuit_id = cur.fetchone()[0]

            # 2. RACES
            round_number = None  # Not provided by OpenF1; never infer from a partial list.

            race_name = f"{YEAR} {session.get('country_name')} Grand Prix"
            race_date = (session.get("date_start") or "")[:10] or None

            cur.execute(
                """
                SELECT race_id FROM races
                WHERE season = %s AND circuit_id = %s AND race_date = %s
                """,
                (YEAR, circuit_id, race_date)
            )
            row = cur.fetchone()

            if row:
                race_id = row[0]
            else:
                cur.execute(
                    """
                    INSERT INTO races
                        (season, round_number, race_name,
                         circuit_id, race_date)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING race_id
                    """,
                    (
                        YEAR, round_number, race_name,
                        circuit_id, race_date
                    )
                )
                race_id = cur.fetchone()[0]

            # 3. SESSIONS
            cur.execute(
                """
                SELECT session_id FROM sessions
                WHERE source_session_key = %s
                """,
                (session_key,)
            )
            row = cur.fetchone()

            if row:
                session_id = row[0]
            else:
                cur.execute(
                    """
                    INSERT INTO sessions
                        (race_id, session_type, session_date,
                         source_session_key, status)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING session_id
                    """,
                    (
                        race_id,
                        session.get("session_type"),
                        session.get("date_start"),
                        session_key,
                        "completed",
                    )
                )
                session_id = cur.fetchone()[0]

            # 4. DRIVERS, TEAMS, SESSION_DRIVERS
            driver_map = {}

            for d in drivers_data:
                number = d.get("driver_number")
                if number is None:
                    continue

                code = d.get("name_acronym")
                name = d.get("full_name") or d.get("broadcast_name")
                if not name:
                    name = f"Driver {number}"

                team_name = d.get("team_name")
                if not team_name:
                    team_name = "Unknown"

                cur.execute(
                    """
                    SELECT driver_id FROM drivers
                    WHERE driver_number = %s
                      AND driver_code IS NOT DISTINCT FROM %s
                    """,
                    (number, code)
                )
                row = cur.fetchone()

                if row:
                    driver_id = row[0]
                else:
                    cur.execute(
                        """
                        INSERT INTO drivers
                            (driver_number, driver_code, driver_name)
                        VALUES (%s, %s, %s)
                        RETURNING driver_id
                        """,
                        (number, code, name)
                    )
                    driver_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO teams (team_name)
                    VALUES (%s)
                    ON CONFLICT (team_name) DO NOTHING
                    """,
                    (team_name,)
                )
                cur.execute(
                    "SELECT team_id FROM teams WHERE team_name = %s",
                    (team_name,)
                )
                team_id = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT session_driver_id
                    FROM session_drivers
                    WHERE session_id = %s AND driver_id = %s
                    """,
                    (session_id, driver_id)
                )
                row = cur.fetchone()

                if row:
                    session_driver_id = row[0]
                else:
                    cur.execute(
                        """
                        INSERT INTO session_drivers
                            (session_id, driver_id, team_id)
                        VALUES (%s, %s, %s)
                        RETURNING session_driver_id
                        """,
                        (session_id, driver_id, team_id)
                    )
                    session_driver_id = cur.fetchone()[0]

                driver_map[number] = session_driver_id

            # 5. LAPS
            inserted = 0

            for lap in laps_data:
                number = lap.get("driver_number")
                session_driver_id = driver_map.get(number)
                lap_number = lap.get("lap_number")

                if session_driver_id is None or lap_number is None:
                    continue

                cur.execute(
                    """
                    INSERT INTO laps (
                        session_driver_id, lap_number,
                        lap_time_seconds, sector1_seconds,
                        sector2_seconds, sector3_seconds,
                        speed_trap_kmh, is_valid
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_driver_id, lap_number)
                    DO UPDATE SET
                        lap_time_seconds = EXCLUDED.lap_time_seconds,
                        sector1_seconds = EXCLUDED.sector1_seconds,
                        sector2_seconds = EXCLUDED.sector2_seconds,
                        sector3_seconds = EXCLUDED.sector3_seconds,
                        speed_trap_kmh = EXCLUDED.speed_trap_kmh,
                        is_valid = EXCLUDED.is_valid
                    """,
                    (
                        session_driver_id,
                        lap_number,
                        lap.get("lap_duration"),
                        lap.get("duration_sector_1"),
                        lap.get("duration_sector_2"),
                        lap.get("duration_sector_3"),
                        lap.get("st_speed"),
                        lap["is_valid"],
                    )
                )
                inserted += 1

    print("\nImport completed successfully!")
    print("Race:", race_name)
    print("Drivers mapped:", len(driver_map))
    print("Lap records processed:", inserted)


if __name__ == "__main__":
    main()
