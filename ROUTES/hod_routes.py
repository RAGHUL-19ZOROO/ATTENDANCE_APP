from flask import Blueprint, render_template, request, jsonify, Response
from core import hod_required, _build_hod_main_dashboard, _get_portal_settings, register_sse_queue, unregister_sse_queue, unlock_requests_collection, publish_sse_event, attendances_collection
import time
import json
from datetime import datetime
from bson.objectid import ObjectId

bp = Blueprint('hod', __name__)


@bp.route('/hod/dashboard')
@hod_required
def hod_dashboard():
    date_text = datetime.now().strftime('%Y-%m-%d')

    data = _build_hod_main_dashboard(date_text)

    # pull pending unlock requests so that HOD can see them on dashboard
    # fetch extra fields so that template can show status/remarks and name
    pending_reqs = list(unlock_requests_collection.find(
        {'status': 'pending'},
        {'_id': 1, 'student_id':1, 'date':1, 'period':1, 'created':1,
         'requested_status':1, 'requested_remarks':1}
    ))
    # convert objectids and dates to serializable values and add student name
    for r in pending_reqs:
        r['request_id'] = str(r.pop('_id'))
        if hasattr(r['date'], 'strftime'):
            r['date'] = r['date'].strftime('%Y-%m-%d')
        # convert created timestamp to iso string
        if hasattr(r.get('created'), 'isoformat'):
            r['created'] = r['created'].isoformat()
        # bring through the requested fields even if empty
        r['requested_status'] = r.get('requested_status', '')
        r['requested_remarks'] = r.get('requested_remarks', '')
        # look up student name
        student_doc = __import__('core').attendances_collection.find_one(
            {'Id': r.get('student_id')}, {'_id':0, 'Name':1}
        )
        r['student_name'] = student_doc.get('Name') if student_doc else ''

    return render_template(
        'hod_dashboard.html',
        selected_date=date_text,
        total_students=data['total_students'],
        present_today=data['present_today'],
        absent_today=data['absent_today'],
        today_absentees=data['today_absentees'],
        long_absentees=data['long_absentees'],
        live_period=data['live_period'],
        unlock_requests=pending_reqs,
    )


@bp.route('/hod/report')
@hod_required
def hod_report_page():

    date_text = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    selected_periods = request.args.getlist('period')

    if not selected_periods or 'all' in selected_periods:
        selected_periods = list(range(1,9))
    else:
        selected_periods = [int(p) for p in selected_periods]

    attendance_date = datetime.strptime(date_text,'%Y-%m-%d')

    rows = []

    for doc in __import__('core').attendances_collection.find({}, {"_id":0}):

        present = 0
        absent = 0
        counted_periods = 0

        # only consider entries that actually exist for the requested date and within selected periods
        for entry in doc.get('attendance',[]):
            if entry.get('date') == attendance_date:
                ep = entry.get('period')
                if ep in selected_periods:
                    counted_periods += 1
                    if entry.get('status') in ['present','late']:
                        present += 1
                    else:
                        absent += 1

        total = counted_periods
        percentage = round((present/total)*100,2) if total else 0

        rows.append({
            'Id': doc.get('Id'),
            'Name': doc.get('Name'),
            'present': present,
            'total': total,
            'absent': absent,
            'percentage': percentage
        })

    return render_template(
        'hod_report.html',
        rows=rows,
        selected_date=date_text,
        selected_periods=selected_periods
    )


@bp.route('/hod/live-data')
@hod_required
def hod_live_data():
    date_text = datetime.now().strftime('%Y-%m-%d')
    data = _build_hod_main_dashboard(date_text)
    return jsonify(data)


@bp.route('/hod/unlock-requests-data')
@hod_required

def unlock_requests_data():
    """Return pending unlock requests as JSON."""
    docs = list(unlock_requests_collection.find(
        {'status':'pending'},
        {'_id':1, 'student_id':1, 'date':1, 'period':1, 'created':1,
         'requested_status':1, 'requested_remarks':1}
    ))
    results = []
    for d in docs:
        entry = {
            'request_id': str(d['_id']),
            'student_id': d.get('student_id'),
            'date': d.get('date').strftime('%Y-%m-%d') if hasattr(d.get('date'), 'strftime') else d.get('date'),
            'period': d.get('period'),
            'created': d.get('created').isoformat() if hasattr(d.get('created'), 'isoformat') else d.get('created'),
            'requested_status': d.get('requested_status', ''),
            'requested_remarks': d.get('requested_remarks', ''),
        }
        # add student name lookup
        student_doc = __import__('core').attendances_collection.find_one(
            {'Id': entry['student_id']}, {'_id':0, 'Name':1}
        )
        entry['student_name'] = student_doc.get('Name') if student_doc else ''
        results.append(entry)
    return jsonify({'ok': True, 'requests': results})




@bp.route('/hod/process-unlock', methods=['POST'])
@hod_required
def process_unlock():

    payload = request.get_json(silent=True) or {}
    req_id = payload.get('request_id')
    action = payload.get('action')

    if not req_id or action not in ['approve', 'reject']:
        return jsonify({'ok': False, 'message': 'Invalid parameters.'}), 400

    try:
        oid = ObjectId(req_id)
    except Exception:
        return jsonify({'ok': False, 'message': 'Bad request id.'}), 400

    req_doc = unlock_requests_collection.find_one({'_id': oid})

    if not req_doc:
        return jsonify({'ok': False, 'message': 'Request not found.'}), 404

    new_status = 'approved' if action == 'approve' else 'rejected'

    # 🔴 Update request status
    unlock_requests_collection.update_one(
        {'_id': oid},
        {'$set': {'status': new_status}}
    )

    # 🔥 IF APPROVED → UPDATE ATTENDANCE STATUS AND REMOVE CONTINUOUS ABSENCE AFTER THIS PERIOD
    if new_status == 'approved':

        student_id = req_doc.get('student_id')
        attendance_date = req_doc.get('date')
        period = req_doc.get('period')
        requested_status = req_doc.get('requested_status')
        requested_remarks = req_doc.get('requested_remarks', '')

        # Update the attendance entry with the requested status and remarks, and unlock it
        attendances_collection.update_one(
            {
                "Id": student_id,
                "attendance": {
                    "$elemMatch": {
                        "date": attendance_date,
                        "period": period
                    }
                }
            },
            {
                "$set": {
                    "attendance.$.status": requested_status,
                    "attendance.$.remarks": requested_remarks,
                    "attendance.$.locked": False
                }
            }
        )

        # Remove auto-marked future absences (if any)
        attendances_collection.update_many(
            {
                "Id": student_id
            },
            {
                "$pull": {
                    "attendance": {
                        "date": attendance_date,
                        "period": {"$gt": period},
                        "status": "absent"
                    }
                }
            }
        )

  
    notify_payload = {
        'type': 'unlock_' + new_status,
        'request_id': req_id
    }

    if req_doc:
        notify_payload.update({
            'student_id': req_doc.get('student_id'),
            'date': req_doc.get('date').strftime('%Y-%m-%d') if hasattr(req_doc.get('date'), 'strftime') else req_doc.get('date'),
            'period': req_doc.get('period'),
        })

    try:
        publish_sse_event(notify_payload)
    except Exception:
        pass

    return jsonify({'ok': True})


@bp.route('/hod/stream')
@hod_required
def hod_stream():
    """Server-Sent Events endpoint for HOD live updates."""
    q = register_sse_queue()

    def gen():
        try:
            while True:
                try:
                    data = q.get(timeout=15)
                except Exception:
                    # send a keep-alive comment
                    yield ': keep-alive\n\n'
                    continue
                yield f'data: {data}\n\n'
        finally:
            unregister_sse_queue(q)

    return Response(gen(), mimetype='text/event-stream')
