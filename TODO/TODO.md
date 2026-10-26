
# RAMP — Team Task Allocation

## Project: Race Strategy Analytics

This document tracks the responsibilities, progress, and pending work for each RAMP team member.

## R — Database & SQL Analytics
**Owner:** [Team Member Name]

- [x] Set up PostgreSQL database.
- [x] Import core Formula 1 race data.
- [x] Import tyre stints, pit stops, weather, and race-control events.
- [x] Create initial SQL analysis queries.
- [ ] Verify table relationships and data integrity.
- [ ] Develop advanced SQL queries using joins, CTEs, window functions, and aggregations.
- [ ] Implement driver performance and lap-time comparisons.
- [ ] Analyze tyre strategies and pit-stop performance.
- [ ] Optimize queries and document findings.

## A — Backend & API Development
**Owner:** [Team Member Name]

- [ ] Set up the FastAPI backend.
- [ ] Configure PostgreSQL connectivity.
- [ ] Implement health-check and race/session endpoints.
- [ ] Implement driver and lap-data endpoints.
- [ ] Implement tyre-stint and pit-stop endpoints.
- [ ] Implement weather and race-control endpoints.
- [ ] Add filtering by race, session, and driver.
- [ ] Validate API responses and handle errors.
- [ ] Test endpoints using Swagger UI.
- [ ] Connect the backend to the frontend.

## M — Frontend & Dashboard
**Owner:** [Team Member Name]

- [x] Set up React and Vite.
- [x] Build the RAMP dashboard layout and sidebar navigation.
- [x] Implement initial charts and dashboard panels.
- [x] Add driver search and selection.
- [ ] Connect the dashboard to the FastAPI backend.
- [ ] Replace demo data with real database data.
- [ ] Make session and driver filters functional with API data.
- [ ] Complete lap analysis, tyre strategy, and pit-stop visualizations.
- [ ] Integrate weather and race-control data.
- [ ] Test responsiveness, loading states, and error handling.

## P — Integration, Testing & Documentation
**Owner:** [Team Member Name]

- [ ] Verify the complete database-to-API-to-frontend workflow.
- [ ] Test API endpoints and SQL query outputs.
- [ ] Validate analytical calculations against source data.
- [ ] Test edge cases and missing data.
- [ ] Maintain project documentation and setup instructions.
- [ ] Update README.md and TODO.md.
- [ ] Add architecture and database schema diagrams.
- [ ] Verify GitHub repository structure and `.gitignore`.
- [ ] Prepare the final demonstration and presentation.

## Shared Responsibilities

- [ ] Review each other's code.
- [ ] Resolve integration issues.
- [ ] Keep the GitHub repository updated.
- [ ] Test the application from a clean setup.
- [ ] Ensure all team members can explain the project architecture and SQL concepts.

## Definition of Done

RAMP is complete when the dashboard displays real Formula 1 data retrieved from PostgreSQL through the API, analytical SQL queries produce verified results, and the full application is documented and ready for demonstration.
