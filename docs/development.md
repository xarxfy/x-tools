# Development

```sh
# Backend (http://127.0.0.1:8080)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
XT_DATA_DIR=./dev-data XT_API_DOCS=true XT_MONITOR=false x-tools serve
pytest

# Frontend (http://127.0.0.1:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

- `XT_MONITOR=false` switches off the background checks (and notifications) – use it with copies of real data.
- Database changes: edit `backend/app/models`, then
  `XT_DATA_DIR=./dev-data alembic revision --autogenerate -m "describe change"`. Migrations run on start.
- UI texts live in `frontend/src/i18n/en.json`.
- There is no CI: run `pytest` and `npm run build` before pushing.
- Changes for users go into `CHANGELOG.md` under *Unreleased*.
- The beta checklist lives in `docs/checklist/checklist.py`; after editing run `python3 docs/checklist/build.py`
  (writes `docs/beta-testing.md`, `docs/beta-checklist.html` and the GitLab/GitHub issue templates).
