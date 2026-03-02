# from flask import Flask, request, jsonify
# import pandas as pd

# app = Flask(__name__)

# EXCEL_FILE = 'attendance.xlsx'

# @app.route('/verify_user', methods=['POST'])
# def verify_user():
#     data = request.json
#     username = str(data.get('username', '')).strip()
#     password = str(data.get('password', '')).strip()

#     try:
#         df = pd.read_excel(EXCEL_FILE, sheet_name='Teachers')
        
#         # Clean the data for matching
#         df['Username'] = df['Username'].astype(str).str.strip()
#         df['Password'] = df['Password'].astype(str).str.strip()

#         # Perform the match using the Username column
#         user_match = df[(df['Username'] == username) & (df['Password'] == password)]

#         if not user_match.empty:
#             # Get the Full Name from the matching row
#             full_name = user_match.iloc[0]['FullName']
#             return jsonify({
#                 "status": "success", 
#                 "full_name": str(full_name) # Send this back to the main backend
#             }), 200
#         else:
#             return jsonify({"status": "fail", "message": "Invalid credentials"}), 401

#     except Exception as e:
#         return jsonify({"status": "error", "message": str(e)}), 500

# if __name__ == '__main__':
#     app.run(port=5001) # Running on a separate port

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyDZBW5-SMRggzxqoAwc9kbaKG4BKGBr6VNfc5pV_dDJAfkz6BaG5Z7TzOUdibZwxXe/exec"

@app.route('/verify_user', methods=['POST'])
def verify_user():
    data = request.json
    params = {
        "action": "verifyTeacher",
        "username": data.get('username', '').strip(),
        "password": data.get('password', '').strip()
    }
    try:
        response = requests.get(APPS_SCRIPT_URL, params=params, timeout=10)
        result = response.json()
        if result.get('status') == 'success':
            return jsonify({"status": "success", "full_name": result.get('full_name')}), 200
        return jsonify({"status": "fail"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5001, debug=True)