# Job Application Tracker

A self-hosted tool for tracking job applications, focused on comparing
**targeted** vs. **sprayed** strategies and measuring conversion rates over
time.

Developed on Windows 11, deployed on a personal Linux home server behind
Tailscale. No public exposure.

## Status

🚧 Track 1 (usable tracker) - in progress.

## Planned architecture

- **Database:** PostgreSQL 16 (Docker)
- **API:** FastAPI + SQLModel
- **UI:** Streamlit
- **Analytics (later):** dbt + Dagster
- **Access:** Tailscale only

## Repo layout

    app/          FastAPI backend
    streamlit/    Streamlit UI
    scripts/      Seed and helper scripts
    .env.example  Config template (real .env is gitignored)

## Running locally

_(filled in during Phase 1)_

## Notes on data

This repo contains **no real job-search data**. Local deployments use a
gitignored Postgres volume. Any demo data is synthetic.