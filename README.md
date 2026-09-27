# MG Screening v2

## New integration

The questionnaire now supports:

- Required user consent before questionnaire submission.
- Consent-based storage of questionnaire answers/results.
- A protected researcher endpoint for accessing stored submissions.
- A copyable `mg-screening-transfer-v1` summary package.
- A handoff to the Eye Movement Observation app when the prototype score is **above 70/110**.

## Render environment variables

Set these in the MG Screening service:

- `EYE_TRACKING_URL` — the deployed URL of the Eye Movement Observation app.
- `MG_ADMIN_ACCESS_TOKEN` — a long random secret used for researcher access to `/api/admin/submissions`.
- `MG_DATABASE_PATH` — optional. Defaults to `mg_screening_data.sqlite3`.

### Important storage note

The included SQLite storage is suitable for local development and prototype testing. A normal Render filesystem is not a permanent database, so for persistent production/research storage, attach a persistent database/storage service before collecting real participant data.

Do not publish the admin token or place it in frontend JavaScript.

## Researcher access

Send the configured token in the `X-Admin-Token` request header when requesting:

`GET /api/admin/submissions`

The endpoint returns only submissions for which the participant gave consent.

This project is a prototype and is not a diagnostic medical device.
