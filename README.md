# Job Application Tracker

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLModel](https://img.shields.io/badge/SQLModel-CA4245?style=for-the-badge)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-6BA81E?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Tailscale](https://img.shields.io/badge/Tailscale-000000?style=for-the-badge&logo=tailscale&logoColor=white)

> I got tired of tracking job applications in a spreadsheet.
> So I built a database, a REST API, a containerized deployment, and a
> nightly backup pipeline.
>
> Normal response, right?

Built to be used, not to be demoed. The portfolio angle is a side effect.

## Status

Track 1 complete and running on a home server. Single user. Reached only
through Tailscale. Track 2 (analytics layer) not started and not needed yet.

## What it does

**Tracking**
- Five statuses: Applied, Screening, Technical, Offer, Rejected
- Two strategies: Targeted vs Sprayed, tracked separately
- Auto-stamped timestamps on every status transition (first response, first
  interview, offer, rejection). Type one field, the API records five
- Auto-scheduled follow-ups per status, overridable
- Notes, salary range, tech stack, contact fields, rejection reason

**Files**
- CV upload per application, stored on disk, path in the DB
- Filenames sanitized on the way in (no `../../etc/passwd` shenanigans)
- Overwriting replaces the old file

**Quality of life**
- Source inference from job URL. LinkedIn, Greenhouse, Pracuj.pl, and a
  dozen more, plus a "Company Site" category for careers pages
- Metric tiles: total, active, interviews, offers, follow-ups due
- Filters by status, strategy, follow-ups-only
- Bulk selection with CSV export and bulk delete
- Stale banner when follow-ups are overdue

## Architecture

### Dev

```text
Windows 11 laptop
├── Python 3.14 venv at repo root
├── Postgres 16 in Docker on 127.0.0.1:5432
├── uvicorn on 127.0.0.1:8050         (terminal 1)
└── Streamlit on 127.0.0.1:8501       (terminal 2)
```

### Prod

```text
Ubuntu 24.04 home server, x86_64, 4 GB RAM
├── Docker Compose
│   ├── job_tracker_db   (postgres:16-alpine, loopback only)
│   ├── job_tracker_api  (FastAPI + uvicorn, internal network only)
│   └── job_tracker_ui   (Streamlit, bound to the Tailscale interface)
├── CVs on /mnt/RedArchive_Hot/Job_tracker/cvs (SSD, bind-mounted)
└── Nightly backups to /mnt/RedArchive_Cold (HDD, separate physical disk)
```

Access is Tailscale-only. The UI listens on the Tailscale IP, not on
`0.0.0.0`. Nothing is port-forwarded. The API and database are not reachable
from the host at all.

## Stack

| Layer | Tool | Version |
|---|---|---|
| DB | Postgres | 16 (alpine) |
| ORM | SQLModel | 0.0.22 (SQLAlchemy 2.0.54) |
| DB driver | psycopg | 3.2.13 (`postgresql+psycopg://`) |
| API | FastAPI | 0.115.12 |
| ASGI | uvicorn | 0.34.0 |
| UI | Streamlit | 1.60.0 |
| Migrations | Alembic | 1.20.0 |
| Python | 3.14.8 | |

Two pins matter. FastAPI 0.115.12 pulls Starlette 0.46, which Streamlit 1.60
needs for `DEFAULT_EXCLUDED_CONTENT_TYPES`. FastAPI 0.115.6 caps Starlette
below that and breaks Streamlit. And `psycopg[binary]` 3.2.13 has a Python
3.14 wheel; 3.2.3 does not.

## Quick start (dev)

Requires Python 3.14, Docker Desktop, Git Bash.

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env if you want a different password

docker compose up -d db
alembic upgrade head

# terminal 1
make api

# terminal 2
make ui
```

Then open `http://localhost:8501`.

Only the `db` container runs during development. The dev API runs bare, which
is faster for reload cycles.

## Deploy (prod)

Assumes Ubuntu, Docker installed, Tailscale up, SSH key added to GitHub.

```bash
git clone git@github.com:SonOfElle/job-tracker.git
cd job-tracker
cp .env.example .env
chmod 600 .env
# edit .env: set POSTGRES_PASSWORD and CV_HOST_PATH

docker compose build
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d
```

The UI is then reachable at the server's Tailscale hostname or IP on port
8501. `CV_HOST_PATH` points at the SSD directory bind-mounted into the
container at `/app/data/cvs`.

The `api` container runs as `uid=1000` so files written to the bind mount are
owned by the server user, not root. The `ui` container runs as root because
it needs a writable home for Streamlit caches and never touches the CV
directory.

## Migrations

Alembic owns the schema. The API does not create tables. On startup it
compares the DB's `alembic_version` to the code's expected head and refuses
to start if they don't match. That catches the three failure modes that
matter: no schema, stale schema, schema ahead of the code (after a rollback).

Typical workflow:

```bash
# on dev
make migrate-new MESSAGE="add interview_round field"
# review migrations/versions/xxx_add_interview_round_field.py
make migrate
# test, commit, push

# on the server
make deploy
make migrate-prod
```

Migrations are copied into the container, so `migrate-prod` runs against the
deploy image without a separate build step.

## Backups

Nightly at 03:00 via cron. A shell script on the server dumps the database,
gzips it, tars the CV directory with the same timestamp, and prunes anything
older than 14 days. Everything lands on the cold-tier HDD, a separate
physical disk from the SSD holding the live database.

**Restore procedure:**

```bash
# stop the API so nothing writes during restore
docker compose stop api

# restore the DB
zcat /mnt/RedArchive_Cold/Backups/job-tracker/jobtracker_YYYY-MM-DD_HHMMSS.sql.gz \
  | docker compose exec -T db psql -U tracker_user -d application_tracker

# restore CVs
tar -xzf /mnt/RedArchive_Cold/Backups/job-tracker/cvs_YYYY-MM-DD_HHMMSS.tar.gz \
  -C /mnt/RedArchive_Hot/Job_tracker/

docker compose start api
```

Restores have been tested. A dump was restored into a scratch database, row
counts compared, scratch dropped. A backup that has never been restored is a
belief, not a fact.

**What this protects against:** disk failure, DB corruption, accidental
deletion, bad migrations.

**What it doesn't:** fire, theft, a PSU that fries both drives. Same machine,
same house. If that matters, add an offsite copy. Nothing here prevents it.

## Design decisions

A few choices worth writing down. Most are a response to a specific problem,
not a preference.

### 1. Alembic before the second schema change

The initial schema came from `SQLModel.metadata.create_all()`, which is fine
while data is fake. It doesn't add columns to existing tables. The first time
I added a field, I would have lost dev data. Alembic went in before the
second schema change, not after. The API now refuses to start against a
mismatched DB, so the failure mode is loud instead of silent.

### 2. Status as VARCHAR + CHECK, not native ENUM

Postgres native ENUMs are painful to modify. Adding a value can't run inside
a transaction on older versions, and removing one is effectively impossible.
A string column with a named `CheckConstraint` gives the same protection at
insert time with none of the operational pain. The statuses aren't going to
change quickly, but "probably won't change" is how you end up doing a
migration you can't easily reverse.

### 3. Auto-stamped timestamps instead of asking the user

I wanted analytics on response times and conversion rates. I didn't want to
type four timestamps per application. The API stamps `first_response_at`,
`first_interview_at`, `offer_at`, and `rejected_at` when status changes. The
semantics stay simple: the timestamps record when the user marked the
transition, not when the employer acted. Good enough for "how long did this
stage take," and it costs zero extra typing. User-set follow-up dates always
win over auto-scheduled ones.

### 4. Source derivation from the URL, not the form

The first version of the form asked me to pick a source from a dropdown every
time. That's a field I'd get wrong or skip. Now the API parses `job_link` and
infers it. LinkedIn, Greenhouse, Pracuj.pl, company career pages, and so on.
If the parse fails or the domain isn't recognized, it falls back to "Other"
or "Company Site" so the analytics still have something to group by. Explicit
user input always wins; the parser only fills in the blank.

### 5. Files on disk, not blobs in Postgres

CVs go to `data/cvs/{application_id}/{filename}`, path in the DB. On prod the
directory is bind-mounted from the SSD archive. Postgres backups stay small,
CVs can be opened without a database query, and a restore of the DB doesn't
require restoring hundreds of binary blobs. The trade-off is that file and DB
can drift. The upload endpoint cleans up the old file on replace, and the
delete endpoint removes it, so drift shouldn't happen in practice.

### 6. No Airflow

4 GB of RAM means Airflow's scheduler, webserver, and metadata DB eat half
the machine. Dagster is lighter and more modern, but for a single nightly job
the honest answer is cron. Track 2 may revisit this if the analytics grow
beyond a handful of scheduled tasks. Until then, cron is enough.

### 7. Loopback-only DB, Tailscale-only UI

The compose file binds Postgres to `127.0.0.1`, not `0.0.0.0`. The UI binds
to the Tailscale IP, not `0.0.0.0`. This cost nothing to set up and took the
server off the internet in two lines. The first version had the UI on
`0.0.0.0`, and the external URL in the logs read as a public IP, which is the
kind of thing you notice late. Bind to the interface you actually use.

## What's not built

Track 2, the analytics layer. When it exists, it'll be a small dbt project
with staging and marts schemas, a nightly snapshot job, and a Streamlit page
or two for funnel analysis and Targeted-vs-Sprayed comparison. On a dataset
this size, it won't be impressive engineering. If I build it, the point is to
build it well, not to build it big.

Smaller things deferred: bulk edit, saved filter presets, calendar view of
follow-ups, email reminders, CSV import from other tools, and a UI
refinement pass based on the annoyance list I've built up from using it.
Each is a real "would be nice." None is blocking daily use, and guessing at
their priority before using the tool for a while is how they all end up
half-built.

---

Built by [@SonOfElle](https://github.com/SonOfElle).

If you're reading this: yes, I know this is overkill for a job
tracker. That's the point.
