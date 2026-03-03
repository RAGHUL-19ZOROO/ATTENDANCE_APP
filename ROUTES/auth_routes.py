from flask import Blueprint, render_template, request, redirect, session, url_for
from core import ROLE_CREDENTIALS, login_required

bp = Blueprint('auth', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/login')
def login_page():
    return render_template('login_select.html')


@bp.route('/login/hod')
def login_hod_page():
    error = request.args.get('error')
    return render_template(
        'register.html',
        error=error,
        role_key='hod',
        role_label='HOD',
        title='HOD Login',
    )


@bp.route('/login/classrep')
def login_classrep_page():
    error = request.args.get('error')
    return render_template(
        'register.html',
        error=error,
        role_key='classrep',
        role_label='Class Rep',
        title='Class Rep Login',
    )


@bp.route('/login/principal')
def login_principal_page():
    error = request.args.get('error')
    return render_template(
        'register.html',
        error=error,
        role_key='principal',
        role_label='Principal',
        title='Principal Login',
    )


@bp.route('/auth/login/<role>', methods=['POST'])
def auth_login(role):
    role = (role or '').lower().strip()
    creds = ROLE_CREDENTIALS.get(role)
    if not creds:
        return redirect(url_for('auth.login_page'))

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if username == creds['username'] and password == creds['password']:
        session['logged_in'] = True
        session['username'] = username
        session['role'] = role
        if role == 'principal':
            return redirect(url_for('principal.principal_settings_page'))
        if role == 'hod':
            return redirect(url_for('hod.hod_dashboard'))
        return redirect(url_for('classrep.classrep_dashboard'))

    if role == 'principal':
        return redirect(url_for('auth.login_principal_page', error='Invalid username or password.'))
    if role == 'hod':
        return redirect(url_for('auth.login_hod_page', error='Invalid username or password.'))
    return redirect(url_for('auth.login_classrep_page', error='Invalid username or password.'))


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.index'))


@bp.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'principal':
        return redirect(url_for('principal.principal_settings_page'))
    if role == 'hod':
        return redirect(url_for('hod.hod_dashboard'))
    return redirect(url_for('classrep.classrep_dashboard'))
