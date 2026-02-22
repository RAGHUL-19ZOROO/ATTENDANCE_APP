from datetime import datetime
from functools import wraps
import os

import pandas as pd
import matplotlib.pyplot as plt

from flask import Flask, jsonify, render_template, request, redirect, session, url_for
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

app = Flask(__name__)
app.secret_key = "attendance-portal-secret-key"

load_dotenv()

HOD_USERNAME = "HOD"
HOD_PASSWORD = "5115"
CLASS_REP_USERNAME = "CLASSREP"
CLASS_REP_PASSWORD = "5115"

ROLE_CREDENTIALS = {
    "hod": {"username": HOD_USERNAME, "password": HOD_PASSWORD},
    "classrep": {"username": CLASS_REP_USERNAME, "password": CLASS_REP_PASSWORD},
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

# Create a new client and connect to the server
client = MongoClient(_mongo_uri, server_api=ServerApi("1"))

# Send a ping to confirm a successful connection
try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as exc:
    print(exc)

db = client["college"]
attendances_collection = db["attendancesAIDS"]
status_options = ["present", "absent", "late"]
period_options = list(range(1, 9))


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
        for entry in doc.get("attendance", []):
            entry_period = entry.get("period", 1)
            if entry.get("date") == attendance_date and entry_period == period:
                rows.append({
                    "Id": student_id,
                    "Name": name,
                    "date": _format_date(entry.get("date")),
                    "period": entry_period,
                    "status": entry.get("status", ""),
                })
                break

    return rows


def _daterange_days(start_date, end_date):
    day_count = (end_date - start_date).days + 1
    for day_offset in range(day_count):
        yield start_date.fromordinal(start_date.toordinal() + day_offset)


def _is_sunday(date_value):
    return date_value.weekday() == 6


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login_page"))
            if session.get("role") != role:
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


hod_required = role_required("hod")
class_rep_required = role_required("classrep")


@app.route("/")
def index():
    return render_template('index.html')


@app.route("/login")
def login_page():
    return render_template("login_select.html")


@app.route("/login/hod")
def login_hod_page():
    error = request.args.get("error")
    return render_template(
        "register.html",
        error=error,
        role_key="hod",
        role_label="HOD",
        title="HOD Login",
    )


@app.route("/login/classrep")
def login_classrep_page():
    error = request.args.get("error")
    return render_template(
        "register.html",
        error=error,
        role_key="classrep",
        role_label="Class Rep",
        title="Class Rep Login",
    )


@app.route("/auth/login/<role>", methods=["POST"])
def auth_login(role):
    role = (role or "").lower().strip()
    creds = ROLE_CREDENTIALS.get(role)
    if not creds:
        return redirect(url_for("login_page"))

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    if username == creds["username"] and password == creds["password"]:
        session["logged_in"] = True
        session["username"] = username
        session["role"] = role
        if role == "hod":
            return redirect(url_for("hod_dashboard"))
        return redirect(url_for("classrep_dashboard"))

    if role == "hod":
        return redirect(url_for("login_hod_page", error="Invalid username or password."))
    return redirect(url_for("login_classrep_page", error="Invalid username or password."))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    if role == "hod":
        return redirect(url_for("hod_dashboard"))
    return redirect(url_for("classrep_dashboard"))


@app.route("/classrep/dashboard")
@class_rep_required
def classrep_dashboard():
    documents = list(attendances_collection.find({}, {"_id": 0}))
    students = attendances_collection.find({}, {"_id": 0, "Id": 1, "Name": 1})
    student_list = [{"Id": s["Id"], "Name": s["Name"]} for s in students]
    student_ids = [s["Id"] for s in student_list]
    attendances = []

    for doc in documents:
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        for entry in doc.get("attendance", []):
            attendances.append({
                "Id": student_id,
                "Name": name,
                "date": _format_date(entry.get("date")),
                "period": entry.get("period", 1),
                "status": entry.get("status", ""),
            })
    return render_template(
        "dashboard.html",
        attendances=attendances,
        students=student_list,
        student_ids=student_ids,
        status_options=status_options,
        period_options=period_options,
    )


@app.route("/classrep/percentage")
@class_rep_required
def classrep_percentage_page():
    return render_template("classrep_percentage.html")


def _build_hod_dashboard_data(date_text):
    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    rows = []
    total_present_hours = 0

    for doc in attendances_collection.find({}, {"_id": 0}):
        periods = {period: "absent" for period in period_options}
        for entry in doc.get("attendance", []):
            entry_period = _parse_period(entry.get("period", 1))
            if entry_period is None:
                continue
            if entry.get("date") == attendance_date:
                periods[entry_period] = entry.get("status", "absent")

        present_hours = sum(1 for status in periods.values() if status in ["present", "late"])
        absent_hours = len(period_options) - present_hours
        day_status = "absent" if absent_hours >= 5 else "present"
        percentage = round((present_hours / len(period_options)) * 100, 2)
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
    total_hours = len(rows) * len(period_options)
    overall_percentage = round((total_present_hours / total_hours) * 100, 2) if total_hours else 0

    return {
        "rows": rows,
        "total_students": len(rows),
        "present_days": present_days,
        "absent_days": absent_days,
        "overall_percentage": overall_percentage,
    }


@app.route("/hod/dashboard")
@hod_required
def hod_dashboard():
    date_text = request.args.get("date")
    if not date_text:
        date_text = datetime.now().strftime("%Y-%m-%d")

    try:
        dashboard_data = _build_hod_dashboard_data(date_text)
    except ValueError:
        date_text = datetime.now().strftime("%Y-%m-%d")
        dashboard_data = _build_hod_dashboard_data(date_text)

    return render_template(
        "hod_dashboard.html",
        selected_date=date_text,
        rows=dashboard_data["rows"],
        total_students=dashboard_data["total_students"],
        present_days=dashboard_data["present_days"],
        absent_days=dashboard_data["absent_days"],
        overall_percentage=dashboard_data["overall_percentage"],
    )

@app.route("/attendance/update", methods=["POST"])
@class_rep_required
def update_attendance():
    payload = request.get_json(silent=True) or {}
    student_id = payload.get("id")
    date_text = payload.get("date")
    period = _parse_period(payload.get("period", 1))
    new_status = payload.get("status")

    if student_id is None or not date_text or new_status not in status_options or period is None:
        return jsonify({"ok": False, "message": "Invalid request."}), 400

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Invalid student ID."}), 400

    if not _is_update_allowed(date_text):
        return jsonify({"ok": False, "message": "Updates allowed only for current date and past dates."}), 403

    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    match = _attendance_match(attendance_date, period)

    result = attendances_collection.update_one(
        {"Id": student_id, "attendance": {"$elemMatch": match}},
        {"$set": {"attendance.$.status": new_status, "attendance.$.period": period}},
    )

    if result.matched_count == 0:
        create_result = attendances_collection.update_one(
            {"Id": student_id},
            {"$push": {"attendance": {"date": attendance_date, "period": period, "status": new_status}}},
        )
        if create_result.matched_count == 0:
            return jsonify({"ok": False, "message": "Student not found."}), 404

    return jsonify({"ok": True, "message": "Status updated."})

@app.route("/attendance/update-bulk", methods=["POST"])
@class_rep_required
def update_attendance_bulk():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates", [])

    if not isinstance(updates, list) or not updates:
        return jsonify({"ok": False, "message": "No updates provided."}), 400

    errors = []
    updated = 0

    for item in updates:
        student_id = item.get("id")
        date_text = item.get("date")
        period = _parse_period(item.get("period", 1))
        new_status = item.get("status")

        if not date_text:
            errors.append({"id": student_id, "message": "Invalid date."})
            continue
        if new_status not in status_options or period is None:
            errors.append({"id": student_id, "message": "Invalid status."})
            continue

        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            errors.append({"id": student_id, "message": "Invalid student ID."})
            continue

        if not _is_update_allowed(date_text):
            errors.append({"id": student_id, "message": "Updates allowed only for current date and past dates."})
            continue

        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
        match = _attendance_match(attendance_date, period)

        result = attendances_collection.update_one(
            {"Id": student_id, "attendance": {"$elemMatch": match}},
            {"$set": {"attendance.$.status": new_status, "attendance.$.period": period}},
        )

        if result.matched_count == 0:
            create_result = attendances_collection.update_one(
                {"Id": student_id},
                {"$push": {"attendance": {"date": attendance_date, "period": period, "status": new_status}}},
            )
            if create_result.matched_count == 0:
                errors.append({"id": student_id, "message": "Student not found."})
                continue

        updated += 1

    return jsonify({
        "ok": len(errors) == 0,
        "updated": updated,
        "errors": errors,
        "message": "Updates processed.",
    })


@app.route("/attendance/ensure-date", methods=["POST"])
@class_rep_required
def ensure_attendance_date():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get("date")
    period = _parse_period(payload.get("period", 1))

    if not date_text or period is None:
        return jsonify({"ok": False, "message": "Date is required."}), 400

    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date."}), 400

    match = _attendance_match(attendance_date, period)

    attendances_collection.update_many(
        {"$nor": [{"attendance": {"$elemMatch": match}}]},
        {"$push": {"attendance": {"date": attendance_date, "period": period, "status": "absent"}}},
    )

    rows = _attendance_rows_for_date(date_text, period)
    return jsonify({"ok": True, "rows": rows})


@app.route("/attendance/mark-all-present", methods=["POST"])
@class_rep_required
def mark_all_present():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get("date")
    period = _parse_period(payload.get("period", 1))

    if not date_text or period is None:
        return jsonify({"ok": False, "message": "Date is required."}), 400

    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date."}), 400

    if not _is_update_allowed(date_text):
        return jsonify({"ok": False, "message": "Updates allowed only for current date and past dates."}), 403

    # Ensure every student has an entry for the given date and period
    match = _attendance_match(attendance_date, period)
    attendances_collection.update_many(
        {"$nor": [{"attendance": {"$elemMatch": match}}]},
        {"$push": {"attendance": {"date": attendance_date, "period": period, "status": "absent"}}},
    )

    # Update all students with "present" status for the given date and period
    attendances_collection.update_many(
        {"attendance": {"$elemMatch": match}},
        {"$set": {"attendance.$.status": "present", "attendance.$.period": period}},
    )

    return jsonify({"ok": True, "message": "All students marked as present."})


@app.route("/attendance/percentage-range", methods=["POST"])
@class_rep_required
def attendance_percentage_range():
    payload = request.get_json(silent=True) or {}
    from_date_text = (payload.get("from_date") or "").strip()
    to_date_text = (payload.get("to_date") or "").strip()

    if not from_date_text:
        return jsonify({"ok": False, "message": "from_date is required."}), 400

    if not to_date_text:
        to_date_text = datetime.now().strftime("%Y-%m-%d")

    try:
        from_date = datetime.strptime(from_date_text, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date_text, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date format. Use YYYY-MM-DD."}), 400

    if from_date > to_date:
        return jsonify({"ok": False, "message": "from_date cannot be greater than to_date."}), 400

    valid_dates = {
        datetime.combine(date_item, datetime.min.time())
        for date_item in _daterange_days(from_date, to_date)
        if not _is_sunday(date_item)
    }
    total_hours = len(valid_dates) * len(period_options)

    if total_hours == 0:
        return jsonify({"ok": False, "message": "Selected range contains only Sundays. No working days to calculate."}), 400

    rows = []
    for doc in attendances_collection.find({}, {"_id": 0}):
        seen_slots = set()
        present_hours = 0

        for entry in doc.get("attendance", []):
            entry_date = entry.get("date")
            entry_period = _parse_period(entry.get("period", 1))
            if entry_date not in valid_dates or entry_period is None:
                continue

            slot_key = (entry_date, entry_period)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)

            if entry.get("status") in ["present", "late"]:
                present_hours += 1

        percentage = round((present_hours / total_hours) * 100, 2) if total_hours else 0
        rows.append({
            "Id": doc.get("Id", ""),
            "Name": doc.get("Name", ""),
            "present_hours": present_hours,
            "total_hours": total_hours,
            "percentage": percentage,
        })

    rows.sort(key=lambda row: row["percentage"], reverse=True)

    return jsonify({
        "ok": True,
        "from_date": from_date_text,
        "to_date": to_date_text,
        "rows": rows,
    })


@app.route("/attendance/chart/<int:student_id>")
@login_required
def student_chart(student_id):
    """Generate a pie chart for a specific student's attendance"""
    import os
    
    student = attendances_collection.find_one({"Id": student_id}, {"_id": 0})
    
    if not student:
        return jsonify({"ok": False, "message": "Student not found."}), 404

    from_date_text = (request.args.get("from_date") or "").strip()
    to_date_text = (request.args.get("to_date") or "").strip()

    from_date = None
    to_date = None
    if from_date_text or to_date_text:
        if not from_date_text or not to_date_text:
            return jsonify({"ok": False, "message": "Both from_date and to_date are required."}), 400
        try:
            from_date = datetime.strptime(from_date_text, "%Y-%m-%d").date()
            to_date = datetime.strptime(to_date_text, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "message": "Invalid date format. Use YYYY-MM-DD."}), 400

        if from_date > to_date:
            return jsonify({"ok": False, "message": "from_date cannot be greater than to_date."}), 400

    status_counts = {"present": 0, "absent": 0, "late": 0}
    for entry in student.get("attendance", []):
        entry_date = entry.get("date")
        if from_date and to_date:
            if not entry_date or not hasattr(entry_date, "date"):
                continue
            entry_day = entry_date.date()
            if entry_day < from_date or entry_day > to_date:
                continue
            if _is_sunday(entry_day):
                continue

        status = entry.get("status", "absent")
        if status in status_counts:
            status_counts[status] += 1

    if sum(status_counts.values()) == 0:
        return jsonify({"ok": False, "message": "No attendance records found in the selected date range."}), 404
    

    plt.figure(figsize=(8, 6))
    colors = ['#4CAF50', '#F44336', '#FF9800']
    plt.pie(status_counts.values(), labels=status_counts.keys(), autopct='%1.1f%%', 
            colors=colors, startangle=90)
    if from_date and to_date:
        plt.title(
            f"Attendance Chart - {student.get('Name', 'Unknown')} (ID: {student_id})\n"
            f"{from_date_text} to {to_date_text}"
        )
    else:
        plt.title(f"Attendance Chart - {student.get('Name', 'Unknown')} (ID: {student_id})")
    
 
    static_dir = os.path.join(app.root_path, 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    if from_date and to_date:
        chart_file = f"chart_{student_id}_{from_date_text}_{to_date_text}.png"
    else:
        chart_file = f"chart_{student_id}.png"

    chart_path = os.path.join(static_dir, chart_file)
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    
    return jsonify({
        "ok": True, 
        "chart_url": url_for('static', filename=chart_file),
        "student_name": student.get('Name', 'Unknown'),
        "stats": status_counts,
        "from_date": from_date_text,
        "to_date": to_date_text,
    })


@app.route("/attendance/chart-page")
@login_required
def chart_page():
    """Render page to select student and view chart"""
    students = list(attendances_collection.find({}, {"_id": 0, "Id": 1, "Name": 1}))
    return render_template("chart.html", students=students)


@app.route("/attendance/by-date/<date_text>")
@login_required
def attendance_by_date(date_text):
    """Get all student attendance for a specific date"""
    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date format."}), 400

    period = _parse_period(request.args.get("period", 1))
    if period is None:
        return jsonify({"ok": False, "message": "Invalid period."}), 400
    
    attendances = []
    
    for doc in attendances_collection.find({}, {"_id": 0}):
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        
        # Find attendance for this date
        status = "absent"  # default
        for entry in doc.get("attendance", []):
            entry_period = entry.get("period", 1)
            if entry.get("date") == attendance_date and entry_period == period:
                status = entry.get("status", "absent")
                break
        
        attendances.append({
            "Id": student_id,
            "Name": name,
            "date": date_text,
            "period": period,
            "status": status
        })
    
    return jsonify({
        "ok": True,
        "date": date_text,
        "period": period,
        "attendances": attendances
    })


@app.route("/attendance/eight-hour-stats")
@login_required
def eight_hour_stats():
    """Get statistics on students with 8 or more hours (days) of attendance"""
    documents = list(attendances_collection.find({}, {"_id": 0}))
    stats = []
    
    for doc in documents:
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        attendance_records = doc.get("attendance", [])
        
        # Count present and late as valid attendance (8-hour equivalent)
        full_day_count = sum(1 for entry in attendance_records 
                            if entry.get("status") in ["present", "late"])
        absent_count = sum(1 for entry in attendance_records 
                          if entry.get("status") == "absent")
        total_days = len(attendance_records)
        
        # Calculate attendance percentage
        attendance_percentage = (full_day_count / total_days * 100) if total_days > 0 else 0
        
        stats.append({
            "Id": student_id,
            "Name": name,
            "full_days": full_day_count,  # 8-hour days
            "absent_days": absent_count,
            "total_days": total_days,
            "percentage": round(attendance_percentage, 2),
            "meets_requirement": full_day_count >= 8  # At least 8 full days
        })
    
    # Sort by full days (descending)
    stats.sort(key=lambda x: x["full_days"], reverse=True)
    
    return jsonify({
        "ok": True,
        "stats": stats,
        "total_students": len(stats),
        "students_meeting_requirement": sum(1 for s in stats if s["meets_requirement"])
    })


@app.route("/attendance/filter-by-hours", methods=["POST"])
@login_required
def filter_by_hours():
    """Filter attendance records by minimum hours/days requirement"""
    payload = request.get_json(silent=True) or {}
    min_days = payload.get("min_days", 8)  # Default to 8 days
    
    try:
        min_days = int(min_days)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Invalid minimum days value."}), 400
    
    documents = list(attendances_collection.find({}, {"_id": 0}))
    filtered_students = []
    
    for doc in documents:
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        attendance_records = doc.get("attendance", [])
        
        # Count full days (present or late)
        full_day_count = sum(1 for entry in attendance_records 
                            if entry.get("status") in ["present", "late"])
        
        if full_day_count >= min_days:
            filtered_students.append({
                "Id": student_id,
                "Name": name,
                "full_days": full_day_count,
                "meets_requirement": True
            })
    
    return jsonify({
        "ok": True,
        "students": filtered_students,
        "min_days_required": min_days,
        "total_meeting_requirement": len(filtered_students)
    })


if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
