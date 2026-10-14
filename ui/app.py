"""Streamlit UI for the Job Application Tracker."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

STRATEGIES = ["Targeted", "Sprayed"]
STATUSES = ["Applied", "Screening", "Technical", "Offer", "Rejected"]
ACTIVE_STATUSES = ["Applied", "Screening", "Technical"]

SOURCES = [
    "LinkedIn", "Indeed", "Glassdoor", "Greenhouse", "Lever", "Workday",
    "Wellfound", "Otta", "Hacker News",
    "Pracuj.pl", "JustJoin.it", "NoFluffJobs", "Bulldogjob", "TheProtocol", "Rocketjobs",
    "Company Site", "Referral", "Recruiter", "Manual", "Other",
]

st.set_page_config(page_title="Job Application Tracker", layout="wide")


# ---------- API helpers ----------------------------------------------------- #

def _handle(resp):
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        st.error(f"{resp.request.method} {resp.url} → {resp.status_code}: {resp.text}")
        return None
    if resp.status_code == 204:
        return True
    return resp.json()


def api_get(path, **params):
    return _handle(requests.get(f"{API_BASE_URL}{path}", params=params, timeout=5))


def api_post(path, payload):
    return _handle(requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=5))


def api_patch(path, payload):
    return _handle(requests.patch(f"{API_BASE_URL}{path}", json=payload, timeout=5))


def api_delete(path):
    return _handle(requests.delete(f"{API_BASE_URL}{path}", timeout=5))


def api_post_cv(app_id, file_obj):
    resp = requests.post(
        f"{API_BASE_URL}/applications/{app_id}/cv",
        files={"file": (file_obj.name, file_obj.getvalue(), "application/octet-stream")},
        timeout=30,
    )
    return _handle(resp)


def api_get_cv_bytes(app_id):
    resp = requests.get(f"{API_BASE_URL}/applications/{app_id}/cv", timeout=10)
    if resp.status_code == 200:
        return resp.content
    return None


# ---------- Formatting helpers ---------------------------------------------- #

def _parse_iso_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _parse_iso_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def format_applied(date_str: str) -> str:
    d = _parse_iso_date(date_str)
    if not d:
        return ""
    days = (date.today() - d).days
    return f"{date_str} ({days}d)"


def format_follow_up(row: dict) -> str:
    nfu = _parse_iso_date(row.get("next_follow_up"))
    if nfu:
        delta = (nfu - date.today()).days
        if delta < 0:
            return f"{nfu.strftime('%b %d')} ({abs(delta)}d overdue)"
        if delta == 0:
            return f"{nfu.strftime('%b %d')} (today)"
        return f"{nfu.strftime('%b %d')} (in {delta}d)"
    status = row.get("status", "")
    ts = {
        "Applied": row.get("created_at"),
        "Screening": row.get("first_response_at"),
        "Technical": row.get("first_interview_at"),
        "Offer": row.get("offer_at"),
        "Rejected": row.get("rejected_at"),
    }.get(status) or row.get("created_at")
    dt = _parse_iso_dt(ts)
    if dt:
        days = (datetime.now(timezone.utc) - dt).days
        return f"Days in status: {days}"
    return ""


# ---------- Table edit callback --------------------------------------------- #

def _on_editor_change():
    edited = st.session_state.get("editor", {}).get("edited_rows") or {}
    df_snapshot = st.session_state.get("_df_snapshot")
    if not edited or df_snapshot is None:
        return

    selected = st.session_state.setdefault("_selected_ids", set())
    failures = 0

    for pos_str, changes in edited.items():
        try:
            pos = int(pos_str)
        except ValueError:
            continue
        if pos >= len(df_snapshot):
            continue
        row = df_snapshot.iloc[pos]
        app_id = int(row["id"])

        if "select" in changes:
            if changes["select"]:
                selected.add(app_id)
            else:
                selected.discard(app_id)

        if "status" in changes:
            new_status = changes["status"]
            if new_status and new_status != row["status"]:
                if api_patch(f"/applications/{app_id}", {"status": new_status}) is None:
                    failures += 1

    if failures:
        st.session_state["_save_error"] = f"{failures} status update(s) failed."


# ---------- Sidebar: add form ----------------------------------------------- #

with st.sidebar:
    st.header("Add application")
    with st.form("add_form", clear_on_submit=True):
        company_name = st.text_input("Company *")
        job_title = st.text_input("Job title *")
        strategy_type = st.selectbox("Strategy", STRATEGIES)
        job_link = st.text_input("Job link")
        source_input = st.selectbox("Source (blank = auto-detect)", [""] + SOURCES)
        salary_range = st.text_input("Salary range")
        tech_stack_raw = st.text_input("Tech stack (comma-separated)")
        date_applied = st.date_input("Date applied", value=date.today())
        contact_name = st.text_input("Contact name")
        contact_email = st.text_input("Contact email")
        has_follow_up = st.checkbox("Set follow-up date")
        next_follow_up = (
            st.date_input("Next follow-up", value=date.today())
            if has_follow_up else None
        )
        notes = st.text_area("Notes")
        cv_file = st.file_uploader("CV (PDF)")
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
                "tech_stack": [s.strip() for s in tech_stack_raw.split(",") if s.strip()],
                "date_applied": date_applied.isoformat(),
                "next_follow_up": next_follow_up.isoformat() if next_follow_up else None,
                "notes": notes or None,
                "contact_name": contact_name or None,
                "contact_email": contact_email or None,
            }
            if source_input:
                payload["source"] = source_input
            result = api_post("/applications", payload)
            if result:
                new_id = result["id"]
                if cv_file is not None:
                    if not api_post_cv(new_id, cv_file):
                        st.warning(f"Application #{new_id} created but CV upload failed.")
                st.success(f"Added: {company_name} — {job_title}")
                st.rerun()


# ---------- Main area ------------------------------------------------------- #

st.title("Job Application Tracker")

applications = api_get("/applications", limit=500) or []

err = st.session_state.pop("_save_error", None)
if err:
    st.error(err)

today_iso = date.today().isoformat()

# Stale banner
overdue = [
    a for a in applications
    if a.get("next_follow_up")
    and a["next_follow_up"] < today_iso
    and a["status"] in ACTIVE_STATUSES
]
if overdue:
    names = ", ".join(f"{a['company_name']} ({a['next_follow_up']})" for a in overdue[:5])
    suffix = f" and {len(overdue) - 5} more" if len(overdue) > 5 else ""
    st.warning(f"⚠️ {len(overdue)} overdue follow-up(s): {names}{suffix}")

# Metrics
total = len(applications)
active = sum(1 for a in applications if a["status"] in ACTIVE_STATUSES)
interviews = sum(1 for a in applications if a["status"] in ("Technical", "Offer"))
offers = sum(1 for a in applications if a["status"] == "Offer")
follow_ups_due = sum(
    1 for a in applications
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
    a for a in applications
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
    selected_ids = st.session_state.get("_selected_ids", set())
    df = pd.DataFrame([
        {
            "select": a["id"] in selected_ids,
            "id": a["id"],
            "company": a["company_name"],
            "title": a["job_title"],
            "link": a.get("job_link") or "",
            "strategy": a["strategy_type"],
            "status": a["status"],
            "applied": format_applied(a["date_applied"]),
            "source": a.get("source") or "",
            "salary": a.get("salary_range") or "",
            "tech": ", ".join(a.get("tech_stack") or []),
            "follow_up": format_follow_up(a),
        }
        for a in filtered
    ])
    st.session_state["_df_snapshot"] = df.copy()

    edited = st.data_editor(
        df,
        column_config={
            "select": st.column_config.CheckboxColumn("", width="small", default=False),
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "company": st.column_config.TextColumn("Company", disabled=True),
            "title": st.column_config.TextColumn("Title", disabled=True),
            "link": st.column_config.LinkColumn("Link", display_text=r"https?://([^/]+)", width="small"),
            "strategy": st.column_config.TextColumn("Strategy", disabled=True, width="small"),
            "status": st.column_config.SelectboxColumn("Status", options=STATUSES, required=True, width="small"),
            "applied": st.column_config.TextColumn("Applied", disabled=True, width="small"),
            "source": st.column_config.TextColumn("Source", disabled=True, width="small"),
            "salary": st.column_config.TextColumn("Salary", disabled=True, width="small"),
            "tech": st.column_config.TextColumn("Tech", disabled=True),
            "follow_up": st.column_config.TextColumn("Follow-up", disabled=True, width="small"),
        },
        hide_index=True,
        use_container_width=True,
        key="editor",
        on_change=_on_editor_change,
    )

    # Bulk actions
    n_sel = len(st.session_state.get("_selected_ids", set()))
    if n_sel > 0:
        st.caption(f"{n_sel} row(s) selected")
        sel_ids = list(st.session_state["_selected_ids"])
        sel_apps = [a for a in applications if a["id"] in sel_ids]
        a1, a2, a3 = st.columns([1, 1, 3])
        with a1:
            if sel_apps:
                csv_df = pd.DataFrame([
                    {
                        "id": a["id"],
                        "company": a["company_name"],
                        "title": a["job_title"],
                        "status": a["status"],
                        "applied": a["date_applied"],
                        "source": a.get("source") or "",
                        "follow_up": a.get("next_follow_up") or "",
                    }
                    for a in sel_apps
                ])
                st.download_button(
                    "Export selected",
                    data=csv_df.to_csv(index=False),
                    file_name=f"applications_{date.today().isoformat()}.csv",
                    mime="text/csv",
                )
        with a2:
            if st.button(f"Delete {n_sel}"):
                st.session_state["_confirm_bulk_delete"] = True

        if st.session_state.get("_confirm_bulk_delete"):
            st.warning(f"Delete {n_sel} application(s)? Cannot be undone.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirm delete", type="primary"):
                    fails = 0
                    for app_id in sel_ids:
                        if api_delete(f"/applications/{int(app_id)}") is None:
                            fails += 1
                    st.session_state["_selected_ids"] = set()
                    st.session_state["_confirm_bulk_delete"] = False
                    if fails:
                        st.error(f"{fails} deletion(s) failed.")
                    else:
                        st.success(f"Deleted {n_sel} application(s).")
                    st.rerun()
            with c2:
                if st.button("Cancel"):
                    st.session_state["_confirm_bulk_delete"] = False
                    st.rerun()


# ---------- Edit panel ------------------------------------------------------ #

st.divider()
st.subheader("Edit an application")

if not applications:
    st.caption("No applications yet.")
else:
    options = {a["id"]: f"#{a['id']} — {a['company_name']} ({a['job_title']})" for a in applications}
    selected_id = st.selectbox(
        "Choose application",
        options=list(options.keys()),
        format_func=lambda x: options[x],
        index=None,
    )

    if selected_id is not None:
        app = next((a for a in applications if a["id"] == selected_id), None)
        if app:
            with st.form(f"edit_form_{selected_id}"):
                e_company = st.text_input("Company", value=app["company_name"])
                e_title = st.text_input("Job title", value=app["job_title"])
                e_strategy = st.selectbox("Strategy", STRATEGIES, index=STRATEGIES.index(app["strategy_type"]))
                e_status = st.selectbox("Status", STATUSES, index=STATUSES.index(app["status"]))
                e_link = st.text_input("Job link", value=app.get("job_link") or "")
                e_source = st.text_input("Source", value=app.get("source") or "")
                e_salary = st.text_input("Salary range", value=app.get("salary_range") or "")
                e_tech = st.text_input("Tech stack (comma-separated)", value=", ".join(app.get("tech_stack") or []))
                e_date = st.date_input("Date applied", value=_parse_iso_date(app["date_applied"]) or date.today())
                e_contact_name = st.text_input("Contact name", value=app.get("contact_name") or "")
                e_contact_email = st.text_input("Contact email", value=app.get("contact_email") or "")
                e_nfu_enabled = st.checkbox("Set follow-up date", value=bool(app.get("next_follow_up")))
                if e_nfu_enabled:
                    e_nfu = st.date_input(
                        "Next follow-up",
                        value=_parse_iso_date(app.get("next_follow_up")) or date.today(),
                    )
                else:
                    e_nfu = None
                e_rejection_reason = st.text_area("Rejection reason", value=app.get("rejection_reason") or "")
                e_notes = st.text_area("Notes", value=app.get("notes") or "")
                e_cv = st.file_uploader("Replace CV")
                save = st.form_submit_button("Save changes", type="primary")

            # CV controls (outside form so they act independently)
            if app.get("cv_filename"):
                st.caption(f"Current CV: {app['cv_filename']}")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button(f"Download CV #{selected_id}"):
                        data = api_get_cv_bytes(selected_id)
                        if data:
                            st.session_state[f"_cv_bytes_{selected_id}"] = data
                        else:
                            st.error("Could not download CV.")
                with cc2:
                    if st.button(f"Delete CV #{selected_id}"):
                        if api_delete(f"/applications/{selected_id}/cv"):
                            st.success("CV deleted.")
                            st.rerun()
                if st.session_state.get(f"_cv_bytes_{selected_id}"):
                    st.download_button(
                        "Save file",
                        data=st.session_state[f"_cv_bytes_{selected_id}"],
                        file_name=app["cv_filename"],
                        mime="application/octet-stream",
                    )

            if save:
                patch = {
                    "company_name": e_company,
                    "job_title": e_title,
                    "strategy_type": e_strategy,
                    "status": e_status,
                    "job_link": e_link or None,
                    "source": e_source or None,
                    "salary_range": e_salary or None,
                    "tech_stack": [s.strip() for s in e_tech.split(",") if s.strip()],
                    "date_applied": e_date.isoformat(),
                    "next_follow_up": e_nfu.isoformat() if e_nfu else None,
                    "contact_name": e_contact_name or None,
                    "contact_email": e_contact_email or None,
                    "rejection_reason": e_rejection_reason or None,
                    "notes": e_notes or None,
                }
                result = api_patch(f"/applications/{selected_id}", patch)
                if result:
                    if e_cv is not None:
                        if not api_post_cv(selected_id, e_cv):
                            st.warning("Fields saved but CV upload failed.")
                    st.success("Saved.")
                    st.rerun()

            st.divider()
            if st.button(f"Delete application #{selected_id}", type="secondary"):
                st.session_state["_confirm_single_delete"] = selected_id
            if st.session_state.get("_confirm_single_delete") == selected_id:
                st.warning(f"Delete application #{selected_id}? Cannot be undone.")
                d1, d2 = st.columns(2)
                with d1:
                    if st.button("Confirm delete", type="primary"):
                        if api_delete(f"/applications/{selected_id}"):
                            st.session_state["_confirm_single_delete"] = None
                            st.session_state.get("_selected_ids", set()).discard(selected_id)
                            st.success("Deleted.")
                            st.rerun()
                with d2:
                    if st.button("Cancel"):
                        st.session_state["_confirm_single_delete"] = None
                        st.rerun()