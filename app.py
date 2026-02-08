from datetime import datetime
from functools import wraps
import pandas as pd
import matplotlib.pyplot as plt
import os

from flask import Flask, jsonify, render_template, request, redirect, session, url_for
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = "attendance-portal-secret-key"

ADMIN_USERNAME = "AIDSHOD"
ADMIN_PASSWORD = "AIDS@5115"

client = MongoClient("mongodb://localhost:27017/")
db = client["college"]
attendances_collection = db["attendancesAIDS"]
status_options = ["present", "absent", "late"]


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


def _attendance_rows_for_date(date_text):
    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    rows = []

    for doc in attendances_collection.find({}, {"_id": 0}):
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        for entry in doc.get("attendance", []):
            if entry.get("date") == attendance_date:
                rows.append({
                    "Id": student_id,
                    "Name": name,
                    "date": _format_date(entry.get("date")),
                    "status": entry.get("status", ""),
                })
                break

    return rows


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
def index():
    return render_template('index.html')


@app.route("/login")
def login_page():
    error = request.args.get("error")
    return render_template("register.html", error=error)


@app.route("/auth/login", methods=["POST"])
def auth_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session["logged_in"] = True
        session["username"] = username
        return redirect(url_for("dashboard"))

    return redirect(url_for("login_page", error="Invalid username or password."))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    documents = list(attendances_collection.find({}, {"_id": 0}))
    students = attendances_collection.find({}, {"_id": 0, "Id": 1, "Name": 1})
    student_list = [{"Id": s["Id"], "Name": s["Name"]} for s in students]
    attendances = []

    for doc in documents:
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        for entry in doc.get("attendance", []):
            attendances.append({
                "Id": student_id,
                "Name": name,
                "date": _format_date(entry.get("date")),
                "status": entry.get("status", ""),
            })
    return render_template(
        "dashboard.html",
        attendances=attendances,
        students=student_list,
        status_options=status_options,
    )

@app.route("/attendance/update", methods=["POST"])
@login_required
def update_attendance():
    payload = request.get_json(silent=True) or {}
    student_id = payload.get("id")
    date_text = payload.get("date")
    new_status = payload.get("status")

    if student_id is None or not date_text or new_status not in status_options:
        return jsonify({"ok": False, "message": "Invalid request."}), 400

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Invalid student ID."}), 400

    if not _is_update_allowed(date_text):
        return jsonify({"ok": False, "message": "Updates allowed only for current date and past dates."}), 403

    attendance_date = datetime.strptime(date_text, "%Y-%m-%d")

    result = attendances_collection.update_one(
        {"Id": student_id, "attendance.date": attendance_date},
        {"$set": {"attendance.$.status": new_status}},
    )

    if result.matched_count == 0:
        return jsonify({"ok": False, "message": "Student not found."}), 404

    return jsonify({"ok": True, "message": "Status updated."})

@app.route("/attendance/update-bulk", methods=["POST"])
@login_required
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
        new_status = item.get("status")

        if not date_text:
            errors.append({"id": student_id, "message": "Invalid date."})
            continue
        if new_status not in status_options:
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

        result = attendances_collection.update_one(
            {"Id": student_id, "attendance.date": attendance_date},
            {"$set": {"attendance.$.status": new_status}},
        )

        if result.matched_count == 0:
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
@login_required
def ensure_attendance_date():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get("date")

    if not date_text:
        return jsonify({"ok": False, "message": "Date is required."}), 400

    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date."}), 400

    attendances_collection.update_many(
        {"attendance": {"$not": {"$elemMatch": {"date": attendance_date}}}},
        {"$push": {"attendance": {"date": attendance_date, "status": "absent"}}},
    )

    rows = _attendance_rows_for_date(date_text)
    return jsonify({"ok": True, "rows": rows})


@app.route("/attendance/mark-all-present", methods=["POST"])
@login_required
def mark_all_present():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get("date")

    if not date_text:
        return jsonify({"ok": False, "message": "Date is required."}), 400

    try:
        attendance_date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid date."}), 400

    if not _is_update_allowed(date_text):
        return jsonify({"ok": False, "message": "Updates allowed only for current date and past dates."}), 403

    # Update all students with "present" status for the given date
    attendances_collection.update_many(
        {"attendance.date": attendance_date},
        {"$set": {"attendance.$.status": "present"}},
    )

    return jsonify({"ok": True, "message": "All students marked as present."})


@app.route("/attendance/chart/<int:student_id>")
@login_required
def student_chart(student_id):
    """Generate a pie chart for a specific student's attendance"""
    import os
    
    student = attendances_collection.find_one({"Id": student_id}, {"_id": 0})
    
    if not student:
        return jsonify({"ok": False, "message": "Student not found."}), 404
    

    status_counts = {"present": 0, "absent": 0, "late": 0}
    for entry in student.get("attendance", []):
        status = entry.get("status", "absent")
        if status in status_counts:
            status_counts[status] += 1
    

    plt.figure(figsize=(8, 6))
    colors = ['#4CAF50', '#F44336', '#FF9800']
    plt.pie(status_counts.values(), labels=status_counts.keys(), autopct='%1.1f%%', 
            colors=colors, startangle=90)
    plt.title(f"Attendance Chart - {student.get('Name', 'Unknown')} (ID: {student_id})")
    
 
    static_dir = os.path.join(app.root_path, 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    chart_path = os.path.join(static_dir, f'chart_{student_id}.png')
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    
    return jsonify({
        "ok": True, 
        "chart_url": url_for('static', filename=f'chart_{student_id}.png'),
        "student_name": student.get('Name', 'Unknown'),
        "stats": status_counts
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
    
    attendances = []
    
    for doc in attendances_collection.find({}, {"_id": 0}):
        student_id = doc.get("Id", "")
        name = doc.get("Name", "")
        
        # Find attendance for this date
        status = "absent"  # default
        for entry in doc.get("attendance", []):
            if entry.get("date") == attendance_date:
                status = entry.get("status", "absent")
                break
        
        attendances.append({
            "Id": student_id,
            "Name": name,
            "date": date_text,
            "status": status
        })
    
    return jsonify({
        "ok": True,
        "date": date_text,
        "attendances": attendances
    })


if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
