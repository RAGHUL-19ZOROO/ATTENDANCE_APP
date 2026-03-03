from datetime import datetime
from functools import wraps
import os

import pandas as pd
import matplotlib.pyplot as plt

from flask import Flask, jsonify, render_template, request, redirect, session, url_for
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from queue import Queue, Empty
import threading
import json as _json

load_dotenv()

app = Flask(__name__)
app.secret_key = "attendance-portal-secret-key"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


HOD_USERNAME = "HOD"
HOD_PASSWORD = "5115"
CLASS_REP_USERNAME = "REP"
CLASS_REP_PASSWORD = "5115"
PRINCIPAL_USERNAME = "PRINCIPAL"
PRINCIPAL_PASSWORD = "5115"

ROLE_CREDENTIALS = {
    "hod": {"username": HOD_USERNAME, "password": HOD_PASSWORD},
    "classrep": {"username": CLASS_REP_USERNAME, "password": CLASS_REP_PASSWORD},
    "principal": {"username": PRINCIPAL_USERNAME, "password": PRINCIPAL_PASSWORD},
}

_mongo_username = os.getenv("MONGODB_USERNAME")
_mongo_password = os.getenv("MONGODB_PASSWORD")
if not _mongo_username or not _mongo_password:
    raise RuntimeError("Missing MONGODB_USERNAME or MONGODB_PASSWORD environment variable.")

_mongo_uri = (
    "mongodb+srv://"
    f"{_mongo_username}:{_mongo_password}"
    "@cluster0.3zsbhl9.mongodb.net/?appName=Cluster0"
)

client = MongoClient(_mongo_uri, server_api=ServerApi("1"))

try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as exc:
    print(exc)


db = client["college"]
attendances_collection = db["attendancesAIDS"]
# new collection to store class-rep unlock requests for locked attendance entries
unlock_requests_collection = db["unlockRequests"]
settings_collection = db["portalSettings"]
status_options = ["present", "absent", "late"]
period_options = list(range(1, 9))
percentage_filter_options = {
    "lt25": "Less than 25%",
    "25to50": "25% and above and less than 50%",
    "50to75": "50% and above and less than 75%",
    "75to100": "75% and above and less than 100%",
    "100plus": "100% and above",
}
SETTINGS_DOC_ID = "global"


def _format_date(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value) if value is not None else ""


def _is_update_allowed(date_text):
    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return False

    today = datetime.now().date()

    return attendance_date <= today


def _parse_period(value):
    try:
        period = int(value)
    except (TypeError, ValueError):
        return None
    return period if 1 <= period <= 8 else None


def _attendance_match(attendance_date, period):
    if period == 1:
        return {
            "date": attendance_date,
            "$or": [
                {"period": 1},
                {"period": {"$exists": False}},
            ],
        }
    return {"date": attendance_date, "period": period}


def _attendance_rows_for_date(date_text, period):
    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    rows = []

    for doc in attendances_collection.find({}, {"_id": 0}):
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")

        entry_found = None
        for entry in doc.get("attendance", []):
            if entry.get("date") == attendance_date and entry.get("period", 1) == period:
                entry_found = entry
                break

        if not entry_found:
            continue

        # 🔒 LOCK RULE:
        # Use stored field if present (added by update endpoints) otherwise default to False
        # (prepopulated rows are not yet 'saved' by the rep)
        locked = entry_found.get('locked', False)

        # If unlock approved → override lock state
        approved = unlock_requests_collection.find_one({
            "student_id": student_id,
            "date": attendance_date,
            "period": period,
            "status": "approved"
        })

        if approved:
            locked = False

        rows.append({
            "Id": student_id,
            "Name": name,
            "date": _format_date(entry_found.get("date")),
            "period": period,
            "status": entry_found.get("status", ""),
            "remarks": entry_found.get("remarks", ""),
            "locked": locked,
            "unlock_requested": False,
        })

    return rows

def _daterange_days(start_date, end_date):
    day_count = (end_date - start_date).days + 1
    for day_offset in range(day_count):
        yield start_date.fromordinal(start_date.toordinal() + day_offset)


def _is_sunday(date_value):
    return date_value.weekday() == 6


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _default_portal_settings():
    return {
        "semester_start": "",
        "semester_end": "",
        "saturday_rules": {},
    }


def _get_portal_settings():
    settings = _default_portal_settings()
    saved = settings_collection.find_one({"_id": SETTINGS_DOC_ID}) or {}
    settings["semester_start"] = saved.get("semester_start", "")
    settings["semester_end"] = saved.get("semester_end", "")
    raw_rules = saved.get("saturday_rules", {})
    if isinstance(raw_rules, dict):
        settings["saturday_rules"] = {
            str(key): bool(value)
            for key, value in raw_rules.items()
        }

    if "saturday_is_leave" in saved and isinstance(saved.get("saturday_is_leave"), bool):
        settings["legacy_saturday_is_leave"] = saved.get("saturday_is_leave")

    return settings


def _save_portal_settings(semester_start, semester_end, saturday_rules):
    settings_collection.update_one(
        {"_id": SETTINGS_DOC_ID},
        {
            "$set": {
                "semester_start": semester_start,
                "semester_end": semester_end,
                "saturday_rules": saturday_rules,
            },
            "$unset": {"saturday_is_leave": ""},
        },
        upsert=True,
    )


def _is_saturday_leave(date_value, saturday_rules=None):
    if date_value.weekday() != 5:
        return False

    rules = saturday_rules or {}
    date_key = date_value.strftime("%Y-%m-%d")
    return bool(rules.get(date_key, False))


def _is_excluded_day(date_value, saturday_rules=None):
    return _is_sunday(date_value) or _is_saturday_leave(date_value, saturday_rules)


def _apply_semester_boundaries(from_date, to_date, settings):
    semester_start = _parse_iso_date(settings.get("semester_start"))
    semester_end = _parse_iso_date(settings.get("semester_end"))

    effective_from = from_date
    effective_to = to_date

    if semester_start and effective_from < semester_start:
        effective_from = semester_start
    if semester_end and effective_to > semester_end:
        effective_to = semester_end

    if effective_from > effective_to:
        return None, None

    return effective_from, effective_to


def _entry_in_settings_window(entry, semester_start, semester_end, saturday_rules):
    entry_date = entry.get("date")
    if not entry_date or not hasattr(entry_date, "date"):
        return False

    day = entry_date.date()
    if semester_start and day < semester_start:
        return False
    if semester_end and day > semester_end:
        return False
    if _is_excluded_day(day, saturday_rules):
        return False
    return True


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.index"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("auth.index"))
            if session.get("role") != role:
                return redirect(url_for("auth.dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


hod_required = role_required("hod")
class_rep_required = role_required("classrep")
principal_required = role_required("principal")


def _parse_percentage_filter(value):
    value = (value or "").strip()
    if not value:
        return None
    return value if value in percentage_filter_options else None


def _matches_percentage_bucket(percentage, bucket):
    if bucket is None:
        return True
    if bucket == "lt25":
        return percentage < 25
    if bucket == "25to50":
        return 25 <= percentage < 50
    if bucket == "50to75":
        return 50 <= percentage < 75
    if bucket == "75to100":
        return 75 <= percentage < 100
    if bucket == "100plus":
        return percentage >= 100
    return True


# Simple in-memory SSE broadcaster (development use only)
_sse_queues = []
_sse_lock = threading.Lock()

def register_sse_queue():
    q = Queue()
    with _sse_lock:
        _sse_queues.append(q)
    return q

def unregister_sse_queue(q):
    with _sse_lock:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass

def publish_sse_event(payload: dict):
    """Publish a JSON payload to all connected SSE clients."""
    text = _json.dumps(payload, default=str)
    with _sse_lock:
        for q in list(_sse_queues):
            try:
                q.put(text)
            except Exception:
                # ignore failures per-queue
                pass


def _build_hod_dashboard_data(date_text, selected_period=None, percentage_filter=None):
    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    rows = []
    total_present_hours = 0

    if selected_period is None:
        periods_to_consider = list(period_options)
    else:
        periods_to_consider = [selected_period]

    total_periods = len(periods_to_consider)
    if total_periods == 0:
        total_periods = len(period_options)
        periods_to_consider = list(period_options)

    for doc in attendances_collection.find({}, {"_id": 0}):
        periods = {period: "absent" for period in periods_to_consider}
        for entry in doc.get("attendance", []):
            entry_period = _parse_period(entry.get("period", 1))
            if entry_period is None:
                continue
            if entry_period not in periods:
                continue
            if entry.get("date") == attendance_date:
                periods[entry_period] = entry.get("status", "absent")

        present_hours = sum(1 for status in periods.values() if status in ["present", "late"])
        absent_hours = total_periods - present_hours
        absent_threshold = 5 if total_periods == len(period_options) else max(1, (total_periods // 2) + 1)
        day_status = "absent" if absent_hours >= absent_threshold else "present"
        percentage = round((present_hours / total_periods) * 100, 2)

        if not _matches_percentage_bucket(percentage, percentage_filter):
            continue

        total_present_hours += present_hours

        rows.append({
            "Id": doc.get("Id", ""),
            "Name": doc.get("Name", ""),
            "present_hours": present_hours,
            "absent_hours": absent_hours,
            "day_status": day_status,
            "percentage": percentage,
        })

    present_days = sum(1 for row in rows if row["day_status"] == "present")
    absent_days = len(rows) - present_days
    total_hours = len(rows) * total_periods
    overall_percentage = round((total_present_hours / total_hours) * 100, 2) if total_hours else 0

    return {
        "rows": rows,
        "total_students": len(rows),
        "present_days": present_days,
        "absent_days": absent_days,
        "overall_percentage": overall_percentage,
    }


def _build_hod_main_dashboard(date_text):
    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")

    total_students = attendances_collection.count_documents({})

    # Check if Period 1 exists
    period1_exists = attendances_collection.count_documents({
        "attendance": {
            "$elemMatch": {
                "date": attendance_date,
                "period": 1
            }
        }
    })

    if period1_exists == 0:
        return {
            "total_students": total_students,
            "present_today": 0,
            "absent_today": 0,
            "today_absentees": [],
            "long_absentees": [],
            "live_period": 0
        }

    today_absentees = []
    total_present_today = 0

    for doc in attendances_collection.find({}, {"_id": 0}):
        student_id = doc.get("Id")
        name = doc.get("Name")

        period1_status = None

        for entry in doc.get("attendance", []):
            if entry.get("date") == attendance_date and entry.get("period") == 1:
                period1_status = entry.get("status")
                break

        if period1_status:
            if period1_status in ["present", "late"]:
                total_present_today += 1
            else:
                today_absentees.append({
                    "Id": student_id,
                    "Name": name
                })

    return {
        "total_students": total_students,
        "present_today": total_present_today,
        "absent_today": len(today_absentees),
        "today_absentees": today_absentees,
        "long_absentees": [],
        "live_period": 1
    }