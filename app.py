import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from flask_caching import Cache
from dotenv import load_dotenv

# 1. Load the environment variables from your .env file
load_dotenv()

app = Flask(__name__)

# It stores data in the computer's RAM.
cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)

# 2. Retrieve variables from the environment
# If 'SECRET_KEY' isn't found in .env, it uses the fallback string provided
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key_for_local_only")

# Retrieve your Apps Script URL
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")

# --- Verification Check (Optional but helpful for debugging) ---
if not APPS_SCRIPT_URL:
    print("Error: APPS_SCRIPT_URL not found in .env file!")


@app.route('/')
def index():
    """Dashboard: Only accessible if logged in."""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_name=session.get('full_name'))


@app.route('/clear_cache')
def clear_cache():
    cache.clear()  # This wipes the entire SimpleCache
    return jsonify({"status": "success", "message": "Cache cleared! Fetching fresh data..."})

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles login by talking DIRECTLY to Google Sheets."""
    if request.method == 'POST':
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        params = {
            "action": "verifyTeacher",
            "username": username,
            "password": password
        }
        
        try:
            response = requests.get(APPS_SCRIPT_URL, params=params, timeout=10)
            result = response.json()

            if result.get('status') == 'success':
                session['user'] = username
                session['full_name'] = result.get('full_name')
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "message": "Invalid Username or Password"})
        
        except Exception as e:
            return jsonify({"success": False, "message": f"Connection Error: {str(e)}"})
            
    return render_template('login.html')

@app.route('/get_classes')
@cache.cached(timeout=6 * 60 * 60)
def get_classes():
    resp = requests.get(f"{APPS_SCRIPT_URL}?action=getClasses")
    return jsonify(resp.json())

# --- RENAMED FOR CONSISTENCY ---
@app.route('/get_timetable')
@cache.cached(timeout=6 * 60 * 60)
def get_timetable_slots():
    """Fetches the slots from the Time_table sheet via Google Apps Script."""
    resp = requests.get(f"{APPS_SCRIPT_URL}?action=getTimetable")
    return jsonify(resp.json())

@app.route('/get_students/<class_name>')
@cache.cached(timeout=6 * 60 * 60)
def get_students(class_name):
    # 'subject' is what the HTML frontend sends, we map it to 'time_table' for Google
    time_table_val = request.args.get('subject') 
    date = request.args.get('date')
    current_teacher = session.get('full_name') 

    url = f"{APPS_SCRIPT_URL}?action=getStudents&className={class_name}&time_table={time_table_val}&date={date}&teacher={current_teacher}"
    
    try:
        resp = requests.get(url, timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"students": [], "already_taken": False, "error": str(e)})

@app.route('/get_teachers')
@cache.cached(timeout=6 * 60 * 60)
def get_teachers():
    """Fetches the list of Full Names from the Teachers sheet via Apps Script."""
    try:
        # Action must match the 'if' block in your Code.gs
        response = requests.get(f"{APPS_SCRIPT_URL}?action=getTeachers", timeout=10)
        teachers = response.json()
        return jsonify(teachers)
    except Exception as e:
        print(f"Error fetching teachers: {e}")
        return jsonify([])

@app.route('/save_attendance', methods=['POST'])
def save_attendance():
    incoming_data = request.json
    
    # 1. Get the data sent from JavaScript
    date_val = incoming_data.get('date')
    time_slot = incoming_data.get('time_slot') # Matches JS payload
    actual_sub = incoming_data.get('actual_subject') # Matches JS payload
    
    # 2. Get teacher from Flask Session (Ensure you are logged in!)
    teacher = session.get('full_name', 'Teacher') 

    # 3. Create the Header - This is where the magic happens
    # Result: 2026-03-02 - 6:00am - 8:00am (རྫོང་ཁ) - Rinchen Namgay
    full_header = f"{date_val} - {time_slot} ({actual_sub}) - {teacher}"
    
    payload = {
        "class_name": incoming_data.get('class_name'),
        "date": date_val,
        "time_table": full_header, # This sends the CLEAN header to Google
        "attendance_data": incoming_data.get('attendance_data')
    }
    
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        return jsonify({"message": "Attendance saved successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_reports')
def get_reports():
    # 1. Get parameters from JavaScript
    cls = request.args.get('class')
    sub = request.args.get('subject', '') 
    view_type = request.args.get('view_type')
    date_val = request.args.get('date')
    teacher = request.args.get('teacher')

    # 2. Use a dictionary for params (This automatically encodes spaces/symbols)
    payload = {
        "action": "getReports",
        "class": cls,
        "subject": sub,
        "view_type": view_type,
        "date": date_val,
        "teacher": teacher
    }
    
    try:
        # 3. Request data. 'params' handles the query string formatting for you.
        response = requests.get(APPS_SCRIPT_URL, params=payload, timeout=20)
        return jsonify(response.json())
    except Exception as e:
        print(f"Flask Error: {e}")
        return jsonify({"error": "Failed to connect to Google Sheets"}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    print("--- Attendance System Main App Running ---")
    app.run(port=5000, debug=True)


# from flask import Flask, render_template, request, jsonify, session, redirect, url_for
# import requests  # Import this to talk to the other backend
# import pandas as pd
# import os
# from datetime import datetime

# app = Flask(__name__)
# app.secret_key = "dfdhjghtutynjhhkuiyturwu667jgdj" # Needed to keep users logged in
# EXCEL_FILE = 'attendance.xlsx'
# AUTH_SERVICE_URL = "http://127.0.0.1:5001/verify_user"

# # --- NEW AUTHENTICATION LOGIC ---


# @app.route('/')
# def index():
#     # 1. If not logged in, redirect to login
#     if 'user' not in session:
#         return redirect(url_for('login'))
    
#     # 2. Get the name from the session
#     teacher_name = session.get('user')
    
#     # 3. Pass it to the index.html template
#     return render_template('index.html', user_name=teacher_name)

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         # Handles the JSON data from your "Sign In" button
#         data = request.json
#         try:
#             # Talks to your Auth Backend on port 5001
#             response = requests.post(AUTH_SERVICE_URL, json=data)
#             if response.status_code == 200:
#                 session['user'] = data.get('username')
#                 return jsonify({"success": True})
#             else:
#                 return jsonify({"success": False, "message": "Invalid Credentials"})
#         except Exception as e:
#             return jsonify({"success": False, "message": "Auth Service Offline"})
    
#     # Handles showing the page when a user visits /login
#     return render_template('login.html')

# @app.route('/logout')
# def logout():
#     session.pop('user', None)
#     return redirect(url_for('login'))

# # --- MODIFIED ROUTES ---

# @app.route('/get_classes')
# def get_classes():
#     """Fetches all sheet names, excluding the Settings sheet."""
#     try:
#         if not os.path.exists(EXCEL_FILE):
#             return jsonify(["Error: File not found"]), 404
#         xl = pd.ExcelFile(EXCEL_FILE)
#         # We filter out 'Settings' so it doesn't appear as a classroom
#         return jsonify([sheet for sheet in xl.sheet_names if sheet != 'Settings'])
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# @app.route('/get_subjects')
# def get_subjects():
#     """Fetches subjects from the Settings sheet."""
#     try:
#         df = pd.read_excel(EXCEL_FILE, sheet_name='Settings')
#         subjects = df['Subjects'].dropna().tolist()
#         return jsonify(subjects)
#     except Exception as e:
#         return jsonify(["General", "Math", "Science"])

# # --- MERGED FUNCTION START ---
# @app.route('/get_students/<class_name>')
# def get_students(class_name):
#     """Checks for existing attendance and returns student list in one go."""
#     try:
#         # 1. Capture query parameters from the frontend
#         date_val = request.args.get('date')
#         subject_val = request.args.get('subject')
#         column_name = f"{date_val} - {subject_val}"

#         # 2. Safety Check: No future dates allowed
#         if date_val:
#             selected_date = datetime.strptime(date_val, '%Y-%m-%d').date()
#             if selected_date > datetime.now().date():
#                 return jsonify({"error": "Future dates are not allowed!"}), 400

#         df = pd.read_excel(EXCEL_FILE, sheet_name=class_name)
        
#         # 3. Check if attendance for this column already exists
#         already_taken = False
#         if column_name in df.columns:
#             # If the column has at least one entry (isn't all empty)
#             if df[column_name].notna().any():
#                 already_taken = True

#         # 4. Prepare student data
#         students = df[['ID', 'Name', 'Phone']].to_dict(orient='records')
        
#         return jsonify({
#             "students": students,
#             "already_taken": already_taken
#         })
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
# # --- MERGED FUNCTION END ---

# @app.route('/save_attendance', methods=['POST'])
# def save_attendance():
#     """Writes attendance to Excel with the teacher's name in the header."""
#     data = request.json
#     class_name = data.get('class_name')
#     date_val = data.get('date')
#     subject = data.get('subject', 'General')
#     records = data.get('attendance_data')
    
#     # 1. Get the logged-in user from the session
#     logged_user = session.get('user', 'Unknown')

#     # 2. Create the combined header: "YYYY-MM-DD - Subject - Teacher"
#     # Example: "2026-03-01 - Morning Prayer - Rinchen"
#     column_name = f"{date_val} - {subject} - {logged_user}"

#     try:
#         with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
#             df = pd.read_excel(EXCEL_FILE, sheet_name=class_name)
            
#             # Ensure the combined column exists
#             if column_name not in df.columns:
#                 df[column_name] = ""

#             # Map statuses to students by ID
#             for s_id, status in records.items():
#                 row_selector = df['ID'] == int(s_id)
#                 df.loc[row_selector, column_name] = status
            
#             df.to_excel(writer, sheet_name=class_name, index=False)
            
#         return jsonify({"message": f"Successfully saved to: {column_name}"})
        
#     except PermissionError:
#         return jsonify({"error": "CLOSE EXCEL! The file is locked."}), 403
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# @app.route('/get_reports')
# def get_reports():
#     class_name = request.args.get('class')
#     subject = request.args.get('subject')
#     date_val = request.args.get('date') # Format: '2026-02'

#     try:
#         df = pd.read_excel(EXCEL_FILE, sheet_name=class_name)
#         matching_cols = [c for c in df.columns if c.startswith(date_val) and subject in c]
        
#         if not matching_cols:
#             return jsonify({"error": "No records found for this period"}), 404
        
#         matching_cols.sort()
#         month_num = date_val.split('-')[1]

#         report_data = []
#         found_headers = [f"{month_num}/{int(c.split(' ')[0].split('-')[2])}" for c in matching_cols]

#         for _, row in df.iterrows():
#             attendance_map = {}
#             # Initialize counters for this student
#             counts = {"P": 0, "A": 0, "S": 0, "L": 0}
            
#             for i, col in enumerate(matching_cols):
#                 status = row[col] if pd.notna(row[col]) else "-"
#                 header_text = found_headers[i]
#                 attendance_map[header_text] = status
                
#                 # Increment counts
#                 if status == "Present": counts["P"] += 1
#                 elif status == "Absent": counts["A"] += 1
#                 elif status == "Sick": counts["S"] += 1
#                 elif status == "Leave": counts["L"] += 1

#             report_data.append({
#                 "ID": row['ID'],
#                 "Name": row['Name'],
#                 "days": attendance_map,
#                 "summary": counts # Send the totals to the frontend
#             })

#         return jsonify({
#             "days_header": found_headers,
#             "records": report_data
#         })
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     app.run(debug=True)