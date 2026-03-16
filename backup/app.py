import os
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from datetime import timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Cache (in-memory) - simple for dev
cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)

# Required secret key
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY must be set in .env. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = SECRET_KEY

# Session cookie security
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Enable this in production when using HTTPS
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes')
# Optional: set session lifetime
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=int(os.getenv('SESSION_LIFETIME_DAYS', '7')))

# CSRF protection
csrf = CSRFProtect(app)

# Apps Script / external service URL
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")
if not APPS_SCRIPT_URL:
    raise RuntimeError("APPS_SCRIPT_URL must be set in .env file!")

# Helper: safe GET to external service with timeout and error handling
def safe_get(url, params=None, timeout=10):
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {'raw': resp.text}
    except requests.RequestException as e:
        # Log server-side; do not expose stack traces to clients
        print(f"HTTP GET error for {url} with params={params}: {e}")
        return None

# Helper: safe POST
def safe_post(url, json=None, timeout=15):
    try:
        resp = requests.post(url, json=json, timeout=timeout)
        resp.raise_for_status()
        try:
            return resp.json(), resp
        except ValueError:
            return {'raw': resp.text}, resp
    except requests.RequestException as e:
        print(f"HTTP POST error for {url} json={json}: {e}")
        return None, None

# Helper: identify AJAX-like requests and request for JSON responses
def is_ajax_request(req):
    # Common header set by many libraries; front-end fetch will set this for API calls
    if req.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    # Or if client expects JSON
    accept = req.headers.get('Accept', '')
    if 'application/json' in accept:
        return True
    # Or if request content-type is application/json
    if req.content_type and 'application/json' in req.content_type:
        return True
    return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            if is_ajax_request(request):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
@login_required
def index():
    return render_template('index.html', user_name=session.get('full_name'))


@app.route('/clear_cache')
@login_required
def clear_cache():
    cache.clear()
    return jsonify({"status": "success", "message": "Cache cleared! Fetching fresh data..."})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400

        # Use POST to avoid leaking credentials in URLs
        params = {"action": "verifyTeacher", "username": username, "password": password}
        result, resp = safe_post(APPS_SCRIPT_URL, json=params, timeout=10)
        if result is None:
            return jsonify({"success": False, "message": "Auth service unavailable"}), 503

        # Expect Apps Script to return a JSON object
        if isinstance(result, dict) and result.get('status') == 'success':
            session['user'] = username
            session['full_name'] = result.get('full_name') or username
            session.permanent = True
            return jsonify({"success": True})

        return jsonify({"success": False, "message": result.get('message') or 'Invalid Username or Password'})

    return render_template('login.html')


@app.route('/get_classes')
@login_required
@cache.cached(timeout=6 * 60 * 60)
def get_classes():
    result = safe_get(APPS_SCRIPT_URL, params={"action": "getClasses"}, timeout=8)
    if result is None:
        return jsonify([])
    return jsonify(result)


@app.route('/get_subjects/<class_name>')
@login_required
def get_subjects(class_name):
    result = safe_get(APPS_SCRIPT_URL, params={"action": "getSubjects", "className": class_name}, timeout=8)
    if result is None:
        return jsonify([])
    if isinstance(result, list):
        return jsonify(result)
    if isinstance(result, dict):
        arr = result.get('result') or result.get('data') or result.get('subjects') or []
        return jsonify(arr if isinstance(arr, list) else [])
    return jsonify([])


@app.route('/get_timetable')
@login_required
@cache.cached(timeout=6 * 60 * 60)
def get_timetable_slots():
    result = safe_get(APPS_SCRIPT_URL, params={"action": "getTimetable"}, timeout=8)
    if result is None:
        return jsonify([])
    return jsonify(result)


@app.route('/get_students/<class_name>')
@login_required
def get_students(class_name):
    # Frontend sends 'subject' query param which is actually the time slot label
    slot = request.args.get('subject')
    date = request.args.get('date')
    teacher_name = session.get('full_name')

    params = {
        "action": "getStudents",
        "className": class_name,
        "time_table": slot,
        "date": date,
        "teacher": teacher_name
    }

    result = safe_get(APPS_SCRIPT_URL, params=params, timeout=12)
    if result is None:
        return jsonify({"students": [], "already_taken": False, "error": "Service unavailable"})
    return jsonify(result)


@app.route('/get_teachers')
@login_required
@cache.cached(timeout=6 * 60 * 60)
def get_teachers():
    result = safe_get(APPS_SCRIPT_URL, params={"action": "getTeachers"}, timeout=8)
    if result is None:
        return jsonify([])
    return jsonify(result)


@app.route('/save_attendance', methods=['POST'])
@login_required
def save_attendance():
    incoming_data = request.get_json(silent=True) or {}

    date_val = incoming_data.get('date')
    time_slot = incoming_data.get('time_slot')
    actual_sub = incoming_data.get('actual_subject')

    teacher = session.get('full_name', 'Teacher')

    full_header = f"{date_val} - {time_slot} ({actual_sub}) - {teacher}"

    payload = {
        "action": "saveAttendance",
        "class_name": incoming_data.get('class_name'),
        "date": date_val,
        "time_table": full_header,
        "attendance_data": incoming_data.get('attendance_data')
    }

    result, resp = safe_post(APPS_SCRIPT_URL, json=payload, timeout=20)
    if result is None:
        return jsonify({"error": "Failed to connect to external service"}), 503

    # If Apps Script indicates exists
    if isinstance(result, dict) and result.get('status') == 'exists':
        return jsonify({"error": "Attendance for this class, date, time slot and teacher is already saved."}), 409

    if resp is not None and not resp.ok:
        return jsonify({"error": result.get('error') or 'Failed to save attendance'}), 500

    return jsonify({"message": "Attendance saved successfully!"})


@app.route('/get_reports')
@login_required
def get_reports():
    cls = request.args.get('class')
    sub = request.args.get('subject', '')
    view_type = request.args.get('view_type')
    date_val = request.args.get('date')
    teacher = request.args.get('teacher')

    params = {
        "action": "getReports",
        "class": cls,
        "subject": sub,
        "view_type": view_type,
        "date": date_val,
        "teacher": teacher
    }

    result = safe_get(APPS_SCRIPT_URL, params=params, timeout=20)
    if result is None:
        return jsonify({"error": "Failed to connect to Google Sheets"}), 500
    return jsonify(result)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'True').lower() in ('1', 'true', 'yes')
    print("--- Attendance System Main App Running ---")
    app.run(port=int(os.getenv('PORT', '5000')), debug=debug)
