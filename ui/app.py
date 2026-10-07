"""Streamlit UI for the Job Application Tracker."""
from __future__ import annotations

import os
from datetime import date

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

STRATEGIES = ["Targeted", "Sprayed"]
STATUSES = ["Applied", "Screening", "Technical", "Offer", "Rejected"]
ACTIVE_STATUSES = ["Applied", "Screening", "Technical"]

st.set_page_config(page_title="Job Application Tracker", layout="wide")


# ---------- API helpers ----------------------------------------------------- #

def _handle(resp: requests.Response):
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        st.error(f"{resp.request.method} {resp.url} → {resp.status_code}: {resp.text}")
        return None
    if resp.status_code == 204:
        return True
    return resp.json()


def api_get(path: str, **params):
    return _handle(requests.get(f"{API_BASE_URL}{path}", params=params, timeout=5))


def api_post(path: str, payload: dict):
    return _handle(requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=5))


def api_patch(path: str, payload: dict):
    return _handle(requests.patch(f"{API_BASE_URL}{path}", json=payload, timeout=5))


# ---------- Sidebar: add form ----------------------------------------------- #

with st.sidebar:
    st.header("Add application")
    with st.form("add_form", clear_on_submit=True):
        company_name = st.text_input("Company *")
        job_title = st.text_input("Job title *")
        strategy_type = st.selectbox("Strategy", STRATEGIES)
        job_link = st.text_input("Job link")
        salary_range = st.text_input("Salary range")
        tech_stack_raw = st.text_input("Tech stack (comma-separated)")
        date_applied = st.date_input("Date applied", value=date.today())
        has_follow_up = st.checkbox("Set follow-up date")
        next_follow_up = (
            st.date_input("Next follow-up", value=date.today())
            if has_follow_up
            else None
        )
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add", type="primary")

    if submitted:
        if not company_name or not job_title:
            st.error("Company and job title are required.")
        else:
            payload = {
                "company_name": company_name,
                "job_title": job_title,
                "strategy_type": strategy_type,
                "job_link": job_link or None,
                "salary_range": salary_range or None,
                "tech_stack": [
                    s.strip() for s in tech_stack_raw.split(",") if s.strip()
                ],
                "date_applied": date_applied.isoformat(),
                "next_follow_up": (
                    next_follow_up.isoformat() if next_follow_up else None
                ),
                "notes": notes or None,
            }
            if api_post("/applications", payload):
                st.success(f"Added: {company_name} — {job_title}")
                st.rerun()


# ---------- Main area ------------------------------------------------------- #

st.title("Job Application Tracker")

applications = api_get("/applications", limit=500) or []

# Metrics row
today_iso = date.today().isoformat()
total = len(applications)
active = sum(1 for a in applications if a["status"] in ACTIVE_STATUSES)
interviews = sum(1 for a in applications if a["status"] in ("Technical", "Offer"))
offers = sum(1 for a in applications if a["status"] == "Offer")
follow_ups_due = sum(
    1
    for a in applications
    if a.get("next_follow_up")
    and a["next_follow_up"] <= today_iso
    and a["status"] in ACTIVE_STATUSES
)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total", total)
m2.metric("Active", active)
m3.metric("Interviews", interviews)
m4.metric("Offers", offers)
m5.metric("Follow-ups due", follow_ups_due)

st.divider()

# Filters
f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    status_filter = st.multiselect("Status", STATUSES, default=STATUSES)
with f2:
    strategy_filter = st.radio("Strategy", ["All"] + STRATEGIES, horizontal=True)
with f3:
    only_follow_ups = st.checkbox("Only follow-ups due", value=False)

filtered = [
    a
    for a in applications
    if a["status"] in status_filter
    and (strategy_filter == "All" or a["strategy_type"] == strategy_filter)
    and (
        not only_follow_ups
        or (
            a.get("next_follow_up")
            and a["next_follow_up"] <= today_iso
            and a["status"] in ACTIVE_STATUSES
        )
    )
]

if not filtered:
    st.info("No applications match the current filters.")
else:
    df = pd.DataFrame(
        [
            {
                "id": a["id"],
                "company": a["company_name"],
                "title": a["job_title"],
                "strategy": a["strategy_type"],
                "status": a["status"],
                "applied": a["date_applied"],
                "follow_up": a["next_follow_up"] or "",
                "salary": a["salary_range"] or "",
                "tech": ", ".join(a.get("tech_stack") or []),
            }
            for a in filtered
        ]
    )

    edited = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "company": st.column_config.TextColumn("Company", disabled=True),
            "title": st.column_config.TextColumn("Title", disabled=True),
            "strategy": st.column_config.TextColumn(
                "Strategy", disabled=True, width="small"
            ),
            "status": st.column_config.SelectboxColumn(
                "Status", options=STATUSES, required=True, width="small"
            ),
            "applied": st.column_config.TextColumn(
                "Applied", disabled=True, width="small"
            ),
            "follow_up": st.column_config.TextColumn(
                "Follow-up", disabled=True, width="small"
            ),
            "salary": st.column_config.TextColumn(
                "Salary", disabled=True, width="small"
            ),
            "tech": st.column_config.TextColumn("Tech", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        key="editor",
    )

    # Diff edited vs original by id (robust to user sorting the grid)
    orig_status = pd.Series(dict(zip(df["id"], df["status"])))
    changed_mask = edited["status"] != edited["id"].map(orig_status)
    changed = edited[changed_mask]

    if not changed.empty:
        if st.button(
            f"Save {len(changed)} status change(s)",
            type="primary",
            key="save_status",
        ):
            failures = 0
            for _, row in changed.iterrows():
                result = api_patch(
                    f"/applications/{int(row['id'])}", {"status": row["status"]}
                )
                if result is None:
                    failures += 1
            if failures == 0:
                st.success(f"Updated {len(changed)} application(s).")
                st.rerun()
            else:
                st.warning(f"{failures} update(s) failed — see errors above.")