# RAMP — Race Strategy Analytics

RAMP is a Formula 1 race strategy analytics platform designed to explore race data, compare driver performance, and analyze tyre strategies, pit stops, weather conditions, and race-control events.

The project combines SQL-based analysis with a web dashboard to make race data easier to explore and interpret.

## Tech Stack

- **Database:** PostgreSQL 18
- **Backend:** Python; FastAPI integration pending
- **Frontend:** React, Vite, JavaScript
- **Charts:** Recharts
- **Icons:** Lucide React
- **Data Source:** [OpenF1 API](https://openf1.org/docs/)

## Features

- Driver and team analysis
- Lap timing and performance comparison
- Tyre stint and compound analysis
- Pit-stop analysis
- Weather condition monitoring
- Race-control event analysis
- Interactive dashboard with charts and navigation
- SQL queries for race data analysis

> **Development status:** The initial database import scripts and frontend dashboard have been developed. Backend integration and live database-driven dashboard functionality remain in progress.

## Project Structure

```text
F1-Analytics/
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── index.css
│   ├── package.json
│   └── ...
├── queries/
│   ├── 01_driver_teams.sql
│   ├── 02_lap_timings.sql
│   ├── 03_race_sessions.sql
│   └── ...
├── .env                 # Local credentials; never commit
├── .gitignore
├── import_f1.py
├── import_remaining.py
├── requirements.txt     # If present
├── README.md
└── TODO.md
```

## Prerequisites

Install the following before setting up RAMP:

- Python 3.11 or a compatible version for the project dependencies
- Node.js and npm
- PostgreSQL
- Git

## Setup Guide

### 1. Clone the repository

```bash
git clone https://github.com/ryanzone/Ramp-F1.git
cd Ramp-F1
```

### 2. Set up PostgreSQL

Create a database named `f1_analytics` using PostgreSQL.

```sql
CREATE DATABASE f1_analytics;
```

Make sure PostgreSQL is running and note your database username, password, host, and port.

### 3. Configure environment variables

Create a `.env` file in the project root.

Add your local PostgreSQL connection details using the variable names expected by the Python scripts.

Example:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=f1_analytics
DB_USER=postgres
DB_PASSWORD=your_local_password
```

**Important:** These are example variable names. If the existing scripts use different names, keep them consistent with the code. Never commit `.env` or publish database credentials.

### 4. Set up the Python environment

From the project root, run:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not present, install the dependencies listed in the project's Python imports and create the file before continuing.

### 5. Import race data

Run the existing import scripts from the project root:

```bash
python import_f1.py
python import_remaining.py
```

These scripts were used to import data for the 2025 Abu Dhabi Grand Prix session, including core race information, laps, tyre stints, pit stops, weather, and race-control events.

Verify that the data was imported successfully before running the analysis queries.

### 6. Run SQL queries

Open PostgreSQL using pgAdmin, psql, or another SQL client.

Connect to `f1_analytics` and execute the SQL files in the `queries/` directory.

The queries are intended to analyze drivers, teams, lap timings, race sessions, and other race data.

### 7. Start the frontend

Open a separate terminal:

```bash
cd frontend
npm install
npm install recharts lucide-react
npm run dev
```

Open the local URL printed by Vite, typically:

```text
http://localhost:5173
```

The current dashboard includes illustrative demo data in some panels. A working frontend does not yet mean that the dashboard is connected to PostgreSQL.

## Data Source

RAMP uses historical Formula 1 data from the [OpenF1 API](https://openf1.org/docs/).

The currently imported session is the 2025 Abu Dhabi Grand Prix. Expanding to other sessions and seasons is part of the planned development.

## Development Roadmap

See [TODO.md](TODO.md) for completed work, remaining tasks, and the recommended implementation order.

## Security

- Keep `.env` out of Git.
- Do not commit passwords, API keys, or other secrets.
- Use environment variables for database credentials.
- Do not expose PostgreSQL directly to the public internet.

## License

No license has been specified yet.
