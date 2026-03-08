from flask import Blueprint, request, jsonify, render_template, url_for
from core import (
    class_rep_required, _parse_period, status_options, attendances_collection,
    _is_update_allowed, _attendance_match, _attendance_rows_for_date, _parse_iso_date,
    _get_portal_settings, _is_saturday_leave, _parse_percentage_filter, _build_hod_dashboard_data,
    hod_required, _build_hod_main_dashboard, login_required, _apply_semester_boundaries,
    _daterange_days, _is_excluded_day, _entry_in_settings_window, period_options,
    unlock_requests_collection
)
from datetime import datetime
import os
import matplotlib.pyplot as plt

bp = Blueprint('attendance', __name__)


def _consume_approved_unlock_request(student_id, attendance_date, period):
    return unlock_requests_collection.find_one_and_update(
        {
            "student_id": student_id,
            "date": attendance_date,
            "period": period,
            "status": "approved"
        },
        {
            "$set": {
                "status": "consumed",
                "consumed": datetime.now(),
            }
        }
    )


@bp.route('/attendance/update', methods=['POST'])
@class_rep_required
def update_attendance():

    payload = request.get_json(silent=True) or {}
    student_id = payload.get('id')
    date_text = payload.get('date')
    period = _parse_period(payload.get('period', 1))
    new_status = payload.get('status')
    remarks = (payload.get('remarks') or '').strip().lower()

    if student_id is None or not date_text or new_status not in status_options or period is None:
        return jsonify({'ok': False, 'message': 'Invalid request.'}), 400

    try:
        student_id = int(student_id)
    except:
        return jsonify({'ok': False, 'message': 'Invalid student ID.'}), 400

    if not _is_update_allowed(date_text):
        return jsonify({'ok': False, 'message': 'Updates allowed only for today and past dates.'}), 403

    attendance_date = datetime.strptime(date_text, '%Y-%m-%d')

    # 🔒 LOCK CHECK
    locked_existing = attendances_collection.find_one({
        "Id": student_id,
        "attendance": {
            "$elemMatch": {
                "date": attendance_date,
                "period": period,
                "locked": True
            }
        }
    })

    # If exists and no approved unlock → block
    if locked_existing:
        approved = _consume_approved_unlock_request(student_id, attendance_date, period)
        if not approved:
            return jsonify({'ok': False, 'message': 'This period is locked.'}), 403

    # Remove old entry for this slot (avoid duplicates)
    attendances_collection.update_one(
        {"Id": student_id},
        {"$pull": {"attendance": {"date": attendance_date, "period": period}}}
    )

    # Save new entry
    attendances_collection.update_one(
        {"Id": student_id},
        {"$push": {
            "attendance": {
                "date": attendance_date,
                "period": period,
                "status": new_status,
                "remarks": remarks,
                "locked": True
            }
        }}
    )

    # 🔁 CONTINUOUS ABSENCE ONLY IF P1 ABSENT
    if new_status == "absent" and period == 1:
        for next_period in range(2, 9):
            attendances_collection.update_one(
                {"Id": student_id},
                {"$pull": {"attendance": {"date": attendance_date, "period": next_period}}}
            )

            attendances_collection.update_one(
                {"Id": student_id},
                {"$push": {
                    "attendance": {
                        "date": attendance_date,
                        "period": next_period,
                        "status": "absent",
                        "remarks": "",
                        "locked": True
                    }
                }}
            )

    # 🔔 Notify HOD
    try:
        from core import publish_sse_event
        publish_sse_event({
            'type': 'attendance_update',
            'id': student_id,
            'date': date_text,
            'period': period
        })
    except:
        pass

    return jsonify({'ok': True, 'message': 'Attendance updated successfully.'})
@bp.route('/attendance/update-bulk', methods=['POST'])
@class_rep_required
def update_attendance_bulk():
    payload = request.get_json(silent=True) or {}
    updates = payload.get('updates', [])

    if not isinstance(updates, list) or not updates:
        return jsonify({'ok': False, 'message': 'No updates provided.'}), 400

    errors = []
    updated = 0
    successful_slots = set()

    for item in updates:
        student_id = item.get('id')
        date_text = item.get('date')
        period = _parse_period(item.get('period', 1))
        new_status = item.get('status')
        remarks = (item.get('remarks') or '').strip().lower()

        if not date_text:
            errors.append({'id': student_id, 'message': 'Invalid date.'})
            continue
        if new_status not in status_options or period is None:
            errors.append({'id': student_id, 'message': 'Invalid status.'})
            continue
        if remarks and remarks not in ['informed', 'on duty']:
            errors.append({'id': student_id, 'message': 'Invalid remarks.'})
            continue

        if remarks == 'informed':
            new_status = 'absent'
        elif remarks == 'on duty':
            new_status = 'present'

        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            errors.append({'id': student_id, 'message': 'Invalid student ID.'})
            continue

        if not _is_update_allowed(date_text):
            errors.append({'id': student_id, 'message': 'Updates allowed only for current date and past dates.'})
            continue

        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')

        locked_existing = attendances_collection.find_one({
            "Id": student_id,
            "attendance": {
                "$elemMatch": {
                    "date": attendance_date,
                    "period": period,
                    "locked": True
                }
            }
        })

        if locked_existing:
            approved = _consume_approved_unlock_request(student_id, attendance_date, period)
            if not approved:
                errors.append({'id': student_id, 'message': 'This period is locked.'})
                continue

        match = _attendance_match(attendance_date, period)

        result = attendances_collection.update_one(
            {'Id': student_id, 'attendance': {'$elemMatch': match}},
            {"$set": {"attendance.$.status": new_status, "attendance.$.period": period, "attendance.$.remarks": remarks, "attendance.$.locked": True}},
        )

        if result.matched_count == 0:
            create_result = attendances_collection.update_one(
                {'Id': student_id},
                {'$push': {'attendance': {'date': attendance_date, 'period': period, 'status': new_status, 'remarks': remarks, 'locked': True}}},
            )
            if create_result.matched_count == 0:
                errors.append({'id': student_id, 'message': 'Student not found.'})
                continue

        updated += 1
        successful_slots.add((attendance_date, period))

    # Lock full saved slots so unchanged rows also require unlock.
    for attendance_date, period in successful_slots:
        match = _attendance_match(attendance_date, period)
        attendances_collection.update_many(
            {'attendance': {'$elemMatch': match}},
            {'$set': {'attendance.$.locked': True, 'attendance.$.period': period}},
        )

    # notify HOD clients (best-effort)
    try:
        from core import publish_sse_event
        publish_sse_event({'type': 'attendance_bulk_update', 'when': datetime.now().isoformat(), 'updated': updated})
    except Exception:
        pass

    return jsonify({
        'ok': len(errors) == 0,
        'updated': updated,
        'errors': errors,
        'message': 'Updates processed.',
    })


@bp.route('/attendance/ensure-date', methods=['POST'])
@class_rep_required
def ensure_attendance_date():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get('date')
    period = _parse_period(payload.get('period', 1))

    if not date_text or period is None:
        return jsonify({'ok': False, 'message': 'Date is required.'}), 400

    try:
        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date.'}), 400

    match = _attendance_match(attendance_date, period)

    attendances_collection.update_many(
        {'$nor': [{'attendance': {'$elemMatch': match}}]},
        {'$push': {'attendance': {'date': attendance_date, 'period': period, 'status': 'present', 'remarks': ''}}},
    )

    rows = _attendance_rows_for_date(date_text, period)
    date_value = attendance_date.date()
    settings = _get_portal_settings()
    saturday_rules = settings.get('saturday_rules', {})

    # notify HOD clients
    try:
        from core import publish_sse_event
        publish_sse_event({'type': 'attendance_ensure_date', 'when': datetime.now().isoformat(), 'date': date_text, 'period': period})
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'rows': rows,
        'is_saturday': date_value.weekday() == 5,
        'saturday_is_leave_for_date': _is_saturday_leave(date_value, saturday_rules),
    })


@bp.route('/attendance/mark-all-present', methods=['POST'])
@class_rep_required
def mark_all_present():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get('date')
    period = _parse_period(payload.get('period', 1))

    if not date_text or period is None:
        return jsonify({'ok': False, 'message': 'Date is required.'}), 400

    try:
        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date.'}), 400

    if not _is_update_allowed(date_text):
        return jsonify({'ok': False, 'message': 'Updates allowed only for current date and past dates.'}), 403

    # Do not allow mark-all once this slot is locked.
    any_locked = attendances_collection.find_one({
        "attendance": {
            "$elemMatch": {
                "date": attendance_date,
                "period": period,
                "locked": True,
            }
        }
    })
    if any_locked:
        return jsonify({
            'ok': False,
            'message': 'This slot is locked. Use unlock request workflow before editing.',
        }), 403

    match = _attendance_match(attendance_date, period)
    attendances_collection.update_many(
        {'$nor': [{'attendance': {'$elemMatch': match}}]},
        {'$push': {'attendance': {'date': attendance_date, 'period': period, 'status': 'present', 'remarks': ''}}},
    )

    attendances_collection.update_many(
        {'attendance': {'$elemMatch': match}},
        {'$set': {'attendance.$.status': 'present', 'attendance.$.period': period, 'attendance.$.locked': True}},
    )

    try:
        from core import publish_sse_event
        publish_sse_event({'type': 'attendance_mark_all_present', 'when': datetime.now().isoformat(), 'date': date_text, 'period': period})
    except Exception:
        pass

    return jsonify({'ok': True, 'message': 'All students marked as present.'})


@bp.route('/attendance/copy-previous-period', methods=['POST'])
@class_rep_required
def copy_previous_period_attendance():
    payload = request.get_json(silent=True) or {}
    date_text = payload.get('date')
    period = _parse_period(payload.get('period', 1))

    if not date_text or period is None:
        return jsonify({'ok': False, 'message': 'Date and period are required.'}), 400

    if period <= 1:
        return jsonify({'ok': False, 'message': 'Previous period is not available for Period 1.'}), 400

    try:
        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date.'}), 400

    if not _is_update_allowed(date_text):
        return jsonify({'ok': False, 'message': 'Updates allowed only for current date and past dates.'}), 403

    previous_period = period - 1
    current_match = _attendance_match(attendance_date, period)
    copied_count = 0

    for doc in attendances_collection.find({}, {"_id": 0, "Id": 1, "attendance": 1}):
        student_id = doc.get("Id")
        if student_id is None:
            continue

        previous_status = "absent"
        for entry in doc.get("attendance", []):
            entry_period = _parse_period(entry.get("period", 1))
            if entry.get("date") == attendance_date and entry_period == previous_period:
                previous_status = entry.get("status", "absent")
                break

        result = attendances_collection.update_one(
            {"Id": student_id, "attendance": {"$elemMatch": current_match}},
            {"$set": {"attendance.$.status": previous_status, "attendance.$.period": period, "attendance.$.locked": True}},
        )

        if result.matched_count == 0:
            attendances_collection.update_one(
                {"Id": student_id},
                {"$push": {"attendance": {"date": attendance_date, "period": period, "status": previous_status, "locked": True}}},
            )

        copied_count += 1

    try:
        from core import publish_sse_event
        publish_sse_event({'type': 'attendance_copy_previous', 'when': datetime.now().isoformat(), 'updated': copied_count, 'date': date_text, 'period': period})
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'message': f'Copied Period {previous_period} attendance to Period {period}.',
        'updated': copied_count,
    })


@bp.route('/attendance/percentage-range', methods=['POST'])
@class_rep_required
def attendance_percentage_range():
    payload = request.get_json(silent=True) or {}
    from_date_text = (payload.get('from_date') or '').strip()
    to_date_text = (payload.get('to_date') or '').strip()

    if not from_date_text:
        return jsonify({'ok': False, 'message': 'from_date is required.'}), 400

    if not to_date_text:
        to_date_text = datetime.now().strftime('%Y-%m-%d')

    try:
        from_date = datetime.strptime(from_date_text, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date_text, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    if from_date > to_date:
        return jsonify({'ok': False, 'message': 'from_date cannot be greater than to_date.'}), 400

    settings = _get_portal_settings()
    effective_from, effective_to = _apply_semester_boundaries(from_date, to_date, settings)

    if effective_from is None or effective_to is None:
        return jsonify({
            'ok': False,
            'message': 'Selected range is outside the semester range set by principal.',
        }), 400

    saturday_rules = settings.get('saturday_rules', {})

    valid_dates = {
        datetime.combine(date_item, datetime.min.time())
        for date_item in _daterange_days(effective_from, effective_to)
        if not _is_excluded_day(date_item, saturday_rules)
    }
    total_hours = len(valid_dates) * len(period_options)

    if total_hours == 0:
        return jsonify({'ok': False, 'message': 'Selected range has no working days (Sundays and Saturday leave days are excluded).'}), 400

    rows = []
    for doc in attendances_collection.find({}, {"_id": 0}):
        seen_slots = set()
        present_hours = 0

        for entry in doc.get('attendance', []):
            entry_date = entry.get('date')
            entry_period = _parse_period(entry.get('period', 1))
            if entry_date not in valid_dates or entry_period is None:
                continue

            slot_key = (entry_date, entry_period)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)

            if entry.get('status') in ['present', 'late']:
                present_hours += 1

        percentage = round((present_hours / total_hours) * 100, 2) if total_hours else 0
        rows.append({
            'Id': doc.get('Id', ''),
            'Name': doc.get('Name', ''),
            'present_hours': present_hours,
            'total_hours': total_hours,
            'percentage': percentage,
        })

    rows.sort(key=lambda row: row['percentage'], reverse=True)

    return jsonify({
        'ok': True,
        'from_date': effective_from.strftime('%Y-%m-%d'),
        'to_date': effective_to.strftime('%Y-%m-%d'),
        'semester_start': settings.get('semester_start', ''),
        'semester_end': settings.get('semester_end', ''),
        'rows': rows,
    })


@bp.route('/attendance/chart/<int:student_id>')
@hod_required
def student_chart(student_id):
    student = attendances_collection.find_one({'Id': student_id}, {'_id': 0})

    if not student:
        return jsonify({'ok': False, 'message': 'Student not found.'}), 404

    from_date_text = (request.args.get('from_date') or '').strip()
    to_date_text = (request.args.get('to_date') or '').strip()

    from_date = None
    to_date = None
    settings = _get_portal_settings()
    saturday_rules = settings.get('saturday_rules', {})

    if from_date_text or to_date_text:
        if not from_date_text or not to_date_text:
            return jsonify({'ok': False, 'message': 'Both from_date and to_date are required.'}), 400
        try:
            from_date = datetime.strptime(from_date_text, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date_text, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'ok': False, 'message': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        if from_date > to_date:
            return jsonify({'ok': False, 'message': 'from_date cannot be greater than to_date.'}), 400

        effective_from, effective_to = _apply_semester_boundaries(from_date, to_date, settings)
        if effective_from is None or effective_to is None:
            return jsonify({
                'ok': False,
                'message': 'Selected range is outside the semester range set by principal.',
            }), 400

        from_date = effective_from
        to_date = effective_to
        from_date_text = from_date.strftime('%Y-%m-%d')
        to_date_text = to_date.strftime('%Y-%m-%d')

    status_counts = {'present': 0, 'absent': 0, 'late': 0}
    for entry in student.get('attendance', []):
        entry_date = entry.get('date')
        if from_date and to_date:
            if not entry_date or not hasattr(entry_date, 'date'):
                continue
            entry_day = entry_date.date()
            if entry_day < from_date or entry_day > to_date:
                continue
            if _is_excluded_day(entry_day, saturday_rules):
                continue

        status = entry.get('status', 'absent')
        if status in status_counts:
            status_counts[status] += 1

    if sum(status_counts.values()) == 0:
        return jsonify({'ok': False, 'message': 'No attendance records found in the selected date range.'}), 404

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

    static_dir = os.path.join('static')
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
        'ok': True, 
        'chart_url': url_for('static', filename=chart_file),
        'student_name': student.get('Name', 'Unknown'),
        'stats': status_counts,
        'from_date': from_date_text,
        'to_date': to_date_text,
    })


@bp.route('/attendance/chart-page')
@hod_required
def chart_page():
    students = list(attendances_collection.find({}, {'_id': 0, 'Id': 1, 'Name': 1}))
    return render_template('chart.html', students=students)


@bp.route('/attendance/by-date/<date_text>')
@login_required
def attendance_by_date(date_text):
    try:
        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date format.'}), 400

    period = _parse_period(request.args.get('period', 1))
    if period is None:
        return jsonify({'ok': False, 'message': 'Invalid period.'}), 400
    
    attendances = []
    
    for doc in attendances_collection.find({}, {'_id': 0}):
        student_id = doc.get('Id', '')
        name = doc.get('Name', '')
        
        # Find attendance for this date
        status = 'absent'  # default
        for entry in doc.get('attendance', []):
            entry_period = entry.get('period', 1)
            if entry.get('date') == attendance_date and entry_period == period:
                status = entry.get('status', 'absent')
                break
        
        attendances.append({
            'Id': student_id,
            'Name': name,
            'date': date_text,
            'period': period,
            'status': status
        })
    
    return jsonify({
        'ok': True,
        'date': date_text,
        'period': period,
        'attendances': attendances
    })


@bp.route('/attendance/eight-hour-stats')
@login_required
def eight_hour_stats():
    documents = list(attendances_collection.find({}, {'_id': 0}))
    stats = []
    settings = _get_portal_settings()
    semester_start = _parse_iso_date(settings.get('semester_start'))
    semester_end = _parse_iso_date(settings.get('semester_end'))
    saturday_rules = settings.get('saturday_rules', {})
    
    for doc in documents:
        student_id = doc.get('Id', '')
        name = doc.get('Name', '')
        attendance_records = [
            entry
            for entry in doc.get('attendance', [])
            if _entry_in_settings_window(entry, semester_start, semester_end, saturday_rules)
        ]
        
        # Count present and late as valid attendance (8-hour equivalent)
        full_day_count = sum(1 for entry in attendance_records 
                            if entry.get('status') in ['present', 'late'])
        absent_count = sum(1 for entry in attendance_records 
                          if entry.get('status') == 'absent')
        total_days = len(attendance_records)
        
        # Calculate attendance percentage
        attendance_percentage = (full_day_count / total_days * 100) if total_days > 0 else 0
        
        stats.append({
            'Id': student_id,
            'Name': name,
            'full_days': full_day_count,  # 8-hour days
            'absent_days': absent_count,
            'total_days': total_days,
            'percentage': round(attendance_percentage, 2),
            'meets_requirement': full_day_count >= 8  # At least 8 full days
        })
    
    # Sort by full days (descending)
    stats.sort(key=lambda x: x['full_days'], reverse=True)
    
    return jsonify({
        'ok': True,
        'stats': stats,
        'total_students': len(stats),
        'students_meeting_requirement': sum(1 for s in stats if s['meets_requirement'])
    })


@bp.route('/attendance/filter-by-hours', methods=['POST'])
@login_required
def filter_by_hours():
    payload = request.get_json(silent=True) or {}
    min_days = payload.get('min_days', 8)
    
    try:
        min_days = int(min_days)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'Invalid minimum days value.'}), 400
    
    documents = list(attendances_collection.find({}, {'_id': 0}))
    filtered_students = []
    settings = _get_portal_settings()
    semester_start = _parse_iso_date(settings.get('semester_start'))
    semester_end = _parse_iso_date(settings.get('semester_end'))
    saturday_rules = settings.get('saturday_rules', {})
    
    for doc in documents:
        student_id = doc.get('Id', '')
        name = doc.get('Name', '')
        attendance_records = [
            entry
            for entry in doc.get('attendance', [])
            if _entry_in_settings_window(entry, semester_start, semester_end, saturday_rules)
        ]
        
        # Count full days (present or late)
        full_day_count = sum(1 for entry in attendance_records 
                            if entry.get('status') in ['present', 'late'])
        
        if full_day_count >= min_days:
            filtered_students.append({
                'Id': student_id,
                'Name': name,
                'full_days': full_day_count,
                'meets_requirement': True
            })
    
    return jsonify({
        'ok': True,
        'students': filtered_students,
        'min_days_required': min_days,
        'total_meeting_requirement': len(filtered_students)
    })
