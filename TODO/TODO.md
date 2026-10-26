# RAMP — Development Roadmap

This file tracks the implementation status and remaining work for RAMP — Race Strategy Analytics.

**Current stage:** Database import scripts and an initial React dashboard are in place. The backend API and complete end-to-end integration remain to be implemented and verified.

## 1. Project Setup and Database

- [x] Create the PostgreSQL database.
- [x] Implement the initial race-data import scripts.
- [x] Import core session, driver, team, and lap data.
- [x] Import tyre stints.
- [x] Import pit stops.
- [x] Import weather samples.
- [x] Import race-control events.
- [x] Create initial SQL analysis queries.
- [ ] Verify all table schemas, foreign keys, and indexes.
- [ ] Add validation for missing, duplicate, or inconsistent records.
- [ ] Test importing a second race session.
- [ ] Support multiple races and seasons.
- [ ] Document the complete database schema.

## 2. Frontend Dashboard

- [x] Set up React and Vite.
- [x] Create the RAMP dashboard layout.
- [x] Add sidebar navigation.
- [x] Add driver search and selection.
- [x] Add lap-performance charts.
- [x] Add tyre strategy visualization.
- [x] Add pit-stop and race-control sections.
- [x] Add responsive styling.
- [ ] Replace illustrative demo data with actual API responses.
- [ ] Populate the session selector using real database sessions.
- [ ] Populate driver and team details dynamically.
- [ ] Add loading, empty-data, and error states where needed.
- [ ] Test all navigation controls and filters.
- [ ] Test the dashboard on different screen sizes.

## 3. FastAPI Backend

- [ ] Create the backend directory and application entry point.
- [ ] Add backend dependencies and a requirements file.
- [ ] Configure PostgreSQL connectivity using environment variables.
- [ ] Implement `GET /api/health`.
- [ ] Implement `GET /api/races`.
- [ ] Implement `GET /api/sessions`.
- [ ] Implement `GET /api/drivers`.
- [ ] Implement `GET /api/laps`.
- [ ] Implement `GET /api/pit-stops`.
- [ ] Implement `GET /api/tyre-stints`.
- [ ] Implement `GET /api/weather`.
- [ ] Implement `GET /api/race-control`.
- [ ] Add query parameters for race, session, and driver filters.
- [ ] Validate request parameters and handle database errors.
- [ ] Configure CORS for the local frontend.
- [ ] Test API responses using FastAPI Swagger UI.

## 4. Frontend–Backend Integration

- [ ] Connect React to the FastAPI endpoints.
- [ ] Remove hardcoded demo datasets from production views.
- [ ] Fetch races and sessions dynamically.
- [ ] Update charts when a session or driver is selected.
- [ ] Connect lap timing charts to actual lap data.
- [ ] Connect tyre strategy views to actual stint data.
- [ ] Connect pit-stop analysis to actual pit-stop records.
- [ ] Connect weather charts to actual weather samples.
- [ ] Connect race-control events to the database.
- [ ] Display clear messages when data is unavailable.
- [ ] Verify that all displayed values match SQL query results.

## 5. Advanced SQL Analytics

- [ ] Add driver lap-time comparisons.
- [ ] Calculate average, fastest, and median lap times.
- [ ] Analyze lap-time consistency and variation.
- [ ] Compare tyre compounds and stint lengths.
- [ ] Calculate pit-stop duration statistics.
- [ ] Analyze performance before and after pit stops.
- [ ] Investigate weather and track-condition relationships with lap times.
- [ ] Analyze race-control events and their timing.
- [ ] Add rankings using window functions.
- [ ] Add CTE-based and multi-table analytical queries.
- [ ] Use views for reusable dashboard calculations.
- [ ] Evaluate indexes and query performance.
- [ ] Document the SQL concepts demonstrated by the project.

## 6. Testing and Reliability

- [ ] Test database connectivity and import scripts.
- [ ] Test API endpoints against an imported session.
- [ ] Test empty datasets and invalid query parameters.
- [ ] Check for duplicate records during repeated imports.
- [ ] Test frontend loading and error handling.
- [ ] Verify calculations against independent SQL queries.
- [ ] Ensure credentials are never exposed in frontend code.
- [ ] Confirm `.env`, `.venv/`, `node_modules/`, and build output are excluded from Git.

## 7. Final Polish and Submission

- [ ] Add dashboard screenshots to the documentation.
- [ ] Document setup instructions for a fresh clone.
- [ ] Add a database schema diagram.
- [ ] Add an architecture diagram.
- [ ] Prepare sample analytical SQL queries and their outputs.
- [ ] Test the full application from a clean setup.
- [ ] Add a project license if required.
- [ ] Review the GitHub repository for secrets and unwanted files.
- [ ] Prepare a project demonstration and presentation.

## Recommended Order

1. Verify the database schema and imported records.
2. Build and test the FastAPI backend.
3. Connect the frontend to the backend.
4. Replace demo data with live database results.
5. Complete advanced SQL analytics.
6. Test, document, and prepare the final demonstration.

## Completion Criteria

RAMP is ready for demonstration when a user can select a real race session, view its drivers and lap data, explore tyre stints and pit stops, inspect weather and race-control events, and see results generated from the PostgreSQL database through the API.
