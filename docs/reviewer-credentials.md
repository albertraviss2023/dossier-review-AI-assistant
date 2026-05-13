# Reviewer Credentials (Synthetic Local Dev)

These are synthetic local-development credentials for dossier assignment and reviewer testing.

- manager (superuser):
  - username: `dachan`
  - password: `123456`

- reviewer/superuser available for review assignment:
  - username: `alutakome`
  - password: `dpar@2026#`
  - scope: `marketing_authorization`

- reviewer:
  - username: `namayanja`
  - password: `Nama@2026#`
  - scope: `marketing_authorization`

- reviewer:
  - username: `kaggwa`
  - password: `Kaggwa@2026#`
  - scope: `marketing_authorization`

Notes:
- Credentials are seeded in `src/dossier_review_ai_assistant/api.py` via `_load_auth_state`.
- Inactive or custom users can still be managed from `/admin.html` by manager `dachan`.
