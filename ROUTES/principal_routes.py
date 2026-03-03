from flask import Blueprint, render_template, request, redirect, url_for
from core import principal_required, _get_portal_settings, _parse_iso_date, _save_portal_settings

bp = Blueprint('principal', __name__)


@bp.route('/principal/settings', methods=['GET', 'POST'])
@principal_required
def principal_settings_page():
    settings = _get_portal_settings()
    if request.method == 'POST':
        semester_start = (request.form.get('semester_start') or '').strip()
        semester_end = (request.form.get('semester_end') or '').strip()

        start_date = _parse_iso_date(semester_start)
        end_date = _parse_iso_date(semester_end)

        if not start_date or not end_date:
            return render_template(
                'principal_settings.html',
                settings=settings,
                error='Please select valid semester start and end dates.',
                message='',
            )

        if start_date > end_date:
            return render_template(
                'principal_settings.html',
                settings=settings,
                error='Semester start date cannot be after semester end date.',
                message='',
            )

        _save_portal_settings(semester_start, semester_end, settings.get('saturday_rules', {}))
        return redirect(url_for('principal.principal_settings_page', message='Semester dates saved successfully.'))

    return render_template(
        'principal_settings.html',
        settings=settings,
        error='',
        message=request.args.get('message', ''),
    )
