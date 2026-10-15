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


def format_timeline(row: dict) -> str:
    d = _parse_iso_date(row.get("date_applied"))
    if not d:
        return ""
    days_applied = (date.today() - d).days
    base = f"{days_applied}d"
    nfu = _parse_iso_date(row.get("next_follow_up"))
    if not nfu:
        return base
    delta = (nfu - date.today()).days
    if delta == 0:
        return f"{base} (=0)"
    if delta > 0:
        return f"{base} (+{delta}d)"
    return f"{base} (-{abs(delta)}d)"


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

        patch = {}
        if "status" in changes:
            new_status = changes["status"]
            if new_status and new_status != row["status"]:
                patch["status"] = new_status
        if "strategy" in changes:
            new_strategy = changes["strategy"]
            if new_strategy and new_strategy != row["strategy"]:
                patch["strategy_type"] = new_strategy
        if patch:
            if api_patch(f"/applications/{app_id}", patch) is None:
                failures += 1

    if failures:
        st.session_state["_save_error"] = f"{failures} status update(s) failed."


# ---------- Sidebar: add form ----------------------------------------------- #

with st.sidebar:
    st.header("Add application")
    with st.form("add_form", clear_on_submit=True, enter_to_submit=False):
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
            }
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

_flash = st.session_state.pop("_flash", None)
if _flash:
    st.toast(_flash["msg"], icon=_flash.get("icon", "✅"))

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
            "title": a["job_title"],
            "company": a["company_name"],
            "status": a["status"],
            "tech": ", ".join(a.get("tech_stack") or []),
            "salary": a.get("salary_range") or "",
            "timeline": format_timeline(a),
            "link": a.get("job_link") or "",
            "strategy": a["strategy_type"],
            "id": a["id"],
        }
        for a in filtered
    ])
    st.session_state["_df_snapshot"] = df.copy()

    edited = st.data_editor(
        df,
        column_config={
            "select": st.column_config.CheckboxColumn("", width="small", default=False),
            "title": st.column_config.TextColumn("Role", disabled=True),
            "company": st.column_config.TextColumn("Company", disabled=True),
            "status": st.column_config.SelectboxColumn("Status", options=STATUSES, required=True, width="small"),
            "tech": st.column_config.TextColumn("Tech", disabled=True),
            "salary": st.column_config.TextColumn("Salary", disabled=True, width="small"),
            "timeline": st.column_config.TextColumn("Timeline", disabled=True, width="small"),
            "link": st.column_config.LinkColumn("Link", display_text=r"https?://([^/]+)", width="small"),
            "strategy": st.column_config.SelectboxColumn("Strategy", options=STRATEGIES, required=True, width="small"),
            "id": None,
        },
        hide_index=True,
        use_container_width=True,
        key="editor",
        on_change=_on_editor_change,
    )

    # Toolbar
    n_sel = len(st.session_state.get("_selected_ids", set()))
    all_ids = {a["id"] for a in filtered}
    n_all = len(all_ids)

    b1, b2, b3, b4, b5, b6 = st.columns([1.4, 1, 1, 1.4, 1, 2])

    with b1:
        if n_sel == n_all and n_all > 0:
            if st.button("Clear", use_container_width=True):
                st.session_state["_selected_ids"] = set()
                st.rerun()
        else:
            if st.button(f"Select all ({n_all})", use_container_width=True):
                st.session_state["_selected_ids"] = set(all_ids)
                st.rerun()

    if n_sel > 0:
        with b2:
            st.caption(f"{n_sel} selected")

        sel_ids = list(st.session_state["_selected_ids"])
        sel_apps = [a for a in applications if a["id"] in sel_ids]

        if n_sel == 1:
            with b3:
                if st.button("Edit", use_container_width=True):
                    st.session_state["_edit_target_id"] = sel_ids[0]
                    st.rerun()
            with b4:
                if sel_apps and sel_apps[0].get("cv_filename"):
                    cv_bytes = api_get_cv_bytes(sel_ids[0])
                    if cv_bytes:
                        st.download_button(
                            "Download CV",
                            data=cv_bytes,
                            file_name=sel_apps[0]["cv_filename"],
                            mime="application/octet-stream",
                            use_container_width=True,
                            key=f"toolbar_cv_{sel_ids[0]}",
                        )
            with b5:
                if st.button("Delete", use_container_width=True):
                    st.session_state["_confirm_bulk_delete"] = True
        else:
            with b3:
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
                        "Export CSV",
                        data=csv_df.to_csv(index=False),
                        file_name=f"applications_{date.today().isoformat()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
            with b4:
                if st.button(f"Delete {n_sel}", use_container_width=True):
                    st.session_state["_confirm_bulk_delete"] = True

    if st.session_state.get("_confirm_bulk_delete"):
        n_del = len(st.session_state.get("_selected_ids", set()))
        st.warning(f"Delete {n_del} application(s)? Cannot be undone.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirm delete", type="primary"):
                fails = 0
                for app_id in list(st.session_state.get("_selected_ids", set())):
                    if api_delete(f"/applications/{int(app_id)}") is None:
                        fails += 1
                st.session_state["_selected_ids"] = set()
                st.session_state["_confirm_bulk_delete"] = False
                if fails:
                    st.error(f"{fails} deletion(s) failed.")
                else:
                    st.success(f"Deleted {n_del} application(s).")
                st.rerun()
        with c2:
            if st.button("Cancel"):
                st.session_state["_confirm_bulk_delete"] = False
                st.rerun()


# ---------- Edit panel ------------------------------------------------------ #

_edit_target = st.session_state.get("_edit_target_id")
if _edit_target is not None:
    app = next((a for a in applications if a["id"] == _edit_target), None)
    if app is None:
        st.session_state["_edit_target_id"] = None
    else:
        selected_id = _edit_target
        st.divider()
        h1, h2 = st.columns([6, 1])
        with h1:
            st.subheader(f"Editing #{selected_id} — {app['company_name']} ({app['job_title']})")
        with h2:
            if st.button("Close", use_container_width=True):
                st.session_state["_edit_target_id"] = None
                st.rerun()

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
            cv_key = f"_cv_bytes_{selected_id}"
            if cv_key not in st.session_state:
                data = api_get_cv_bytes(selected_id)
                if data is not None:
                    st.session_state[cv_key] = data
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.session_state.get(cv_key):
                    st.download_button(
                        "Download CV",
                        data=st.session_state[cv_key],
                        file_name=app["cv_filename"],
                        mime="application/octet-stream",
                        use_container_width=True,
                        key=f"edit_cv_{selected_id}",
                    )
                else:
                    st.button("Download CV", disabled=True, use_container_width=True)
            with cc2:
                if st.button(f"Delete CV", use_container_width=True):
                    if api_delete(f"/applications/{selected_id}/cv"):
                        st.session_state.pop(cv_key, None)
                        st.session_state["_flash"] = {"msg": "CV deleted.", "icon": "✅"}
                        st.rerun()

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
            current = {
                "company_name": app["company_name"],
                "job_title": app["job_title"],
                "strategy_type": app["strategy_type"],
                "status": app["status"],
                "job_link": app.get("job_link") or None,
                "source": app.get("source") or None,
                "salary_range": app.get("salary_range") or None,
                "tech_stack": app.get("tech_stack") or [],
                "date_applied": app["date_applied"],
                "next_follow_up": app.get("next_follow_up"),
                "contact_name": app.get("contact_name") or None,
                "contact_email": app.get("contact_email") or None,
                "rejection_reason": app.get("rejection_reason") or None,
                "notes": app.get("notes") or None,
            }
            if patch == current and e_cv is None:
                st.session_state["_flash"] = {"msg": "No changes to save.", "icon": "ℹ️"}
                st.rerun()
            result = api_patch(f"/applications/{selected_id}", patch)
            if result:
                if e_cv is not None:
                    if not api_post_cv(selected_id, e_cv):
                        st.session_state["_flash"] = {"msg": "Fields saved but CV upload failed.", "icon": "⚠️"}
                    else:
                        st.session_state.pop(f"_cv_bytes_{selected_id}", None)
                        st.session_state["_flash"] = {"msg": "Saved.", "icon": "✅"}
                else:
                    st.session_state["_flash"] = {"msg": "Saved.", "icon": "✅"}
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