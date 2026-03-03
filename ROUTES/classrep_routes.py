from flask import Blueprint, render_template, request, jsonify, Response
from core import class_rep_required, _get_portal_settings, _attendance_match, attendances_collection, _attendance_rows_for_date, _parse_iso_date, _is_saturday_leave, status_options, period_options, unlock_requests_collection, register_sse_queue, unregister_sse_queue
from datetime import datetime
import json


bp = Blueprint('classrep', __name__)


@bp.route('/classrep/dashboard')
@class_rep_required
def classrep_dashboard():
    settings = _get_portal_settings()
    default_date_text = datetime.now().strftime('%Y-%m-%d')
    default_period = 1
    default_attendance_date = datetime.strptime(default_date_text, '%Y-%m-%d')
    default_match = _attendance_match(default_attendance_date, default_period)

    attendances_collection.update_many(
        {"$nor": [{"attendance": {"$elemMatch": default_match}}]},
        # insert default row; not locked until the rep saves an update
        {"$push": {"attendance": {"date": default_attendance_date, "period": default_period, "status": "absent", "locked": False}}},
    )

    students = attendances_collection.find({}, {"_id": 0, "Id": 1, "Name": 1})
    student_list = [{"Id": s["Id"], "Name": s["Name"]} for s in students]
    student_ids = [s["Id"] for s in student_list]
    attendances = _attendance_rows_for_date(default_date_text, default_period)

    return render_template(
        'dashboard.html',
        settings=settings,
        attendances=attendances,
        students=student_list,
        student_ids=student_ids,
        status_options=status_options,
        period_options=period_options,
    )


@bp.route('/classrep/percentage')
@class_rep_required
def classrep_percentage_page():
    settings = _get_portal_settings()
    return render_template('classrep_percentage.html', settings=settings)


@bp.route('/classrep/settings/saturday', methods=['POST'])
@class_rep_required
def update_saturday_leave_setting():
    payload = request.get_json(silent=True) or {}
    date_text = (payload.get('date') or '').strip()

    if not date_text:
        return jsonify({'ok': False, 'message': 'Date is required.'}), 400

    selected_date = _parse_iso_date(date_text)
    if selected_date is None:
        return jsonify({'ok': False, 'message': 'Invalid date.'}), 400
    if selected_date.weekday() != 5:
        return jsonify({'ok': False, 'message': 'Saturday leave option can be changed only for Saturday dates.'}), 400

    saturday_is_leave = bool(payload.get('saturday_is_leave', False))
    settings = _get_portal_settings()
    saturday_rules = dict(settings.get('saturday_rules', {}))
    saturday_rules[selected_date.strftime('%Y-%m-%d')] = saturday_is_leave

    from core import _save_portal_settings

    _save_portal_settings(
        settings.get('semester_start', ''),
        settings.get('semester_end', ''),
        saturday_rules,
    )
    return jsonify({
        'ok': True,
        'date': selected_date.strftime('%Y-%m-%d'),
        'saturday_is_leave': saturday_is_leave,
        'message': 'Saturday leave preference saved.',
    })


@bp.route('/classrep/unlock-request', methods=['POST'])
@class_rep_required

def submit_unlock_request():
    """Class rep asks HOD to unlock a previously locked attendance slot."""
    payload = request.get_json(silent=True) or {}
    student_id = payload.get('id')
    date_text = payload.get('date')
    period = _parse_iso_date(date_text) and payload.get('period')
    try:
        period = int(period) if period is not None else None
    except (TypeError, ValueError):
        period = None

    # new status / remarks supplied by class rep when requesting unlock
    requested_status = payload.get('requested_status')
    requested_remarks = (payload.get('requested_remarks') or '').strip().lower()

    if student_id is None or not date_text or period is None or requested_status not in status_options:
        return jsonify({'ok': False, 'message': 'Invalid request.'}), 400

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'Invalid student ID.'}), 400

    try:
        # keep a full datetime for compatibility with other records
        attendance_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid date.'}), 400

    # prevent duplicate pending requests
    existing = unlock_requests_collection.find_one({
        'student_id': student_id,
        'date': attendance_date,
        'period': period,
        'status': 'pending',
    })
    if existing:
        return jsonify({'ok': False, 'message': 'A pending unlock request already exists for this entry.'}), 409

    unlock_requests_collection.insert_one({
        'student_id': student_id,
        'date': attendance_date,
        'period': period,
        'requested_status': requested_status,
        'requested_remarks': requested_remarks,
        'status': 'pending',
        'created': datetime.now(),
    })

    # notify all clients (including HOD and rep) about new unlock request
    try:
        from core import publish_sse_event
        publish_sse_event({
            'type': 'unlock_request',
            'when': datetime.now().isoformat(),
            'student_id': student_id,
            'date': date_text,
            'period': period,
        })
    except Exception:
        pass

    return jsonify({'ok': True, 'message': 'Unlock request submitted.'})


@bp.route('/classrep/stream')
@class_rep_required

def classrep_stream():
    """SSE endpoint for class-rep to receive real-time events."""
    q = register_sse_queue()
    def gen():
        try:
            while True:
                try:
                    data = q.get(timeout=15)
                except Exception:
                    yield ': keep-alive\n\n'
                    continue
                yield f'data: {data}\n\n'
        finally:
            unregister_sse_queue(q)
    return Response(gen(), mimetype='text/event-stream')
