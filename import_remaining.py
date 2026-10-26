import os
import time
import requests
import psycopg
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API = "https://api.openf1.org/v1"

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "f1_analytics"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}


def fetch(endpoint, session_key):
    response = requests.get(
        f"{API}/{endpoint}",
        params={"session_key": session_key},
        timeout=60,
    )
    response.raise_for_status()
    time.sleep(1.1)  # Stay within the free API request limit
    return response.json()


with psycopg.connect(**db_config) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT session_id, source_session_key
            FROM sessions
            WHERE session_type = 'Race'
            ORDER BY session_date DESC
            LIMIT 1
        """)
        session = cur.fetchone()

        if not session:
            raise RuntimeError("No Race session found in the sessions table.")

        session_id, session_key = session
        cur.execute("""
    DELETE FROM pit_stops
    WHERE session_driver_id IN (
        SELECT session_driver_id
        FROM session_drivers
        WHERE session_id = %s
    )
""", (session_id,))

        cur.execute("""
            DELETE FROM tyre_stints
            WHERE session_driver_id IN (
                SELECT session_driver_id
                FROM session_drivers
                WHERE session_id = %s
            )
        """, (session_id,))

        cur.execute(
            "DELETE FROM weather_samples WHERE session_id = %s",
            (session_id,)
        )

        cur.execute(
            "DELETE FROM race_control_events WHERE session_id = %s",
            (session_id,)
        )
        print(f"Importing session key: {session_key}")

        # Map OpenF1 driver numbers to our session-driver records
        cur.execute("""
            SELECT d.driver_number, sd.session_driver_id, d.driver_id
            FROM session_drivers sd
            JOIN drivers d ON d.driver_id = sd.driver_id
            WHERE sd.session_id = %s
        """, (session_id,))

        driver_map = {
            int(number): (sd_id, driver_id)
            for number, sd_id, driver_id in cur.fetchall()
        }

        # 1. Tyre stints
        for row in fetch("stints", session_key):
            mapping = driver_map.get(row.get("driver_number"))
            if not mapping:
                continue

            sd_id, _ = mapping
            cur.execute("""
                INSERT INTO tyre_stints
                    (session_driver_id, stint_number, compound,
                     start_lap, end_lap, starting_tyre_age)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                sd_id, row.get("stint_number"), row.get("compound"),
                row.get("lap_start"), row.get("lap_end"),
                row.get("tyre_age_at_start"),
            ))

        print("Tyre stints imported.")

        # 2. Pit stops
        for row in fetch("pit", session_key):
            mapping = driver_map.get(row.get("driver_number"))
            if not mapping:
                continue

            sd_id, _ = mapping
            cur.execute("""
                INSERT INTO pit_stops
                    (session_driver_id, lap_number, stop_number,
                     lane_duration_seconds, stop_duration_seconds,
                     pit_timestamp)
                VALUES (
                    %s, %s,
                    (SELECT COUNT(*) + 1 FROM pit_stops
                     WHERE session_driver_id = %s),
                    %s, %s, %s
                )
            """, (
                sd_id, row.get("lap_number"), sd_id,
                row.get("lane_duration"), row.get("stop_duration"),
                row.get("date"),
            ))

        print("Pit stops imported.")

        # 3. Weather samples
        for row in fetch("weather", session_key):
            cur.execute("""
                INSERT INTO weather_samples
                    (session_id, recorded_at, air_temperature,
                     track_temperature, humidity, rainfall, wind_speed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, row.get("date"), row.get("air_temperature"),
                row.get("track_temperature"), row.get("humidity"),
                bool(row["rainfall"]) if row.get("rainfall") is not None else None,
row.get("wind_speed"),
            ))

        print("Weather samples imported.")

        # 4. Race-control events
        for row in fetch("race_control", session_key):
            driver_number = row.get("driver_number")
            mapping = driver_map.get(driver_number) if driver_number else None
            driver_id = mapping[1] if mapping else None

            cur.execute("""
                INSERT INTO race_control_events
                    (session_id, driver_id, recorded_at, lap_number,
                     category, flag, scope, sector, message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, driver_id, row.get("date"),
                row.get("lap_number"), row.get("category"),
                row.get("flag"), row.get("scope"),
                row.get("sector"), row.get("message"),
            ))

        print("Race-control events imported.")

print("Import complete.")