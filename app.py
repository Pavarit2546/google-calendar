import time
from flask import Flask, request, redirect, jsonify, session, url_for, render_template_string
import requests
import os
import webbrowser
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_ID = os.getenv("CLIENT_ID") 
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT")
AUTH_URL = os.getenv("AUTH_URL")
CALENDAR_API_BASE = os.getenv("CALENDAR_API_BASE")

GLOBAL_REFRESH_TOKEN = None
GLOBAL_ACCESS_TOKEN_CACHE = None
# -----------------------------------------------------

# 1. 🔑 Endpoint สำหรับเริ่มการยืนยันตัวตน
@app.route('/auth/google')
def google_auth():
    """สร้าง URL สำหรับให้ผู้ใช้กดยืนยันสิทธิ์"""
    # ** ⚠️ ต้องแทนที่ YOUR_NGROK_URL ด้วย URL จริงที่ได้จาก ngrok **
    # REDIRECT_URI = f"{request.url_root.strip('/')}/auth/google/callback"
    REDIRECT_URI = os.getenv("REDIRECT_URI")
    
    # สร้าง URL สำหรับส่งผู้ใช้ไปที่ Google
    auth_params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/calendar',
        'access_type': 'offline', # สำคัญมากในการขอ Refresh Token
        'prompt': 'consent'      # แนะนำให้ขอสิทธิ์ทุกครั้งในขั้นตอนทดสอบ
    }
    
    # สร้าง Query String และ Redirect
    query_string = requests.compat.urlencode(auth_params)
    full_auth_url = f"{AUTH_URL}?{query_string}"
    
    print(f"Redirecting user to: {full_auth_url}")
    #return แบบ JSON (สำหรับทดสอบ) มันจะส่งเป็น body แทนการ redirect
    # return jsonify({
    #     "status": "success",
    #     "authorization_url": full_auth_url
    # })
    return redirect(full_auth_url)

# 2. 🚀 Endpoint ใหม่สำหรับ Workflow (สั่งเปิดเบราว์เซอร์โดยตรง)
@app.route('/auth/google/open')
def google_auth_open():
    """สร้าง URL, สั่งเปิดเบราว์เซอร์โดยตรง, และส่ง URL กลับเป็น JSON"""
    
    REDIRECT_URI = os.getenv("REDIRECT_URI")
    
    auth_params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/calendar',
        'access_type': 'offline', 
        'prompt': 'consent'
    }
    
    query_string = requests.compat.urlencode(auth_params)
    full_auth_url = f"{AUTH_URL}?{query_string}"
    
    # ** 💥 คำสั่งที่สั่งเปิดเบราว์เซอร์โดยตรง 💥 **
    # *คำเตือน: คำสั่งนี้รันบนเครื่องที่รัน Backend นี้เท่านั้น (เครื่อง Local ของคุณ)*
    try:
        webbrowser.open(full_auth_url)
        print(f"Browser opened for OAuth: {full_auth_url}")
        status_msg = "Browser opened for authorization."
    except Exception as e:
        print(f"ERROR opening browser: {e}")
        
    return jsonify({
        "authorization_url": full_auth_url
    })
    

# Endpoint สำหรับ Workflow (รับ client id และ client secret จาก workflow)
# @app.route('/auth/google/open', methods=['GET', 'POST'])
# def google_auth_open():
#     # ⚠️ รับ Credentials จาก Query/Body แทน Global
#     client_id = request.args.get('client_id') or request.json.get('client_id')
#     client_secret = request.args.get('client_secret') or request.json.get('client_secret')
    
#     REDIRECT_URI = f"https://ab54a051b8b4.ngrok-free.app/auth/google/callback"
    
#     # 1. สร้าง Full Auth URL
#     auth_params = {
#         'client_id': client_id,
#         'client_secret': client_secret,
#         'redirect_uri': REDIRECT_URI,
#         'response_type': 'code',
#         'scope': 'https://www.googleapis.com/auth/calendar',
#         'access_type': 'offline', 
#         'prompt': 'consent'
#     }
    
#     query_string = requests.compat.urlencode(auth_params)
#     full_auth_url = f"{AUTH_URL}?{query_string}"
    
#     # 2. สั่งเปิดเบราว์เซอร์ (สำหรับเครื่อง Local)
#     try:
#         webbrowser.open(full_auth_url)
#         print(f"Browser opened for OAuth: {full_auth_url}")
#         status_msg = "Browser opened for authorization."
#     except Exception as e:
#         print(f"ERROR opening browser: {e}")
    
#     # 3. ส่ง URL ที่สร้างเสร็จแล้วกลับไปให้ Workflow (เพื่อใช้ในการ Debug/ยืนยัน)
#     return jsonify({
#         "authorization_url": full_auth_url
#     })

## 3. 🎣 Endpoint Callback (redirect_uri)
@app.route('/auth/google/callback')
def google_callback():
    """รับ Code และแลกเปลี่ยนเป็น Access Token และ Refresh Token"""
    global GLOBAL_REFRESH_TOKEN
    global GLOBAL_ACCESS_TOKEN_CACHE
    
    # 1. รับ Authorization Code
    auth_code = request.args.get('code')
    if not auth_code:
        return "Authorization Code not found.", 400

    REDIRECT_URI = os.getenv("REDIRECT_URI")
    
    # 2. ยิง POST Request ไปที่ Token Endpoint เพื่อแลก Code
    token_data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    token_response = requests.post(TOKEN_ENDPOINT, data=token_data)
    token_info = token_response.json()
    
    if token_response.status_code != 200:
        print("TOKEN EXCHANGE ERROR RESPONSE:", token_response.text)
        return jsonify({"error": "Token exchange failed", "details": token_info}), 500

    # 3. จัดเก็บ Refresh Token
    # เก็บ Refresh Token ไว้ใช้ในอนาคต (ในระบบจริงควรเก็บใน DB)
    if 'refresh_token' in token_info:
        GLOBAL_REFRESH_TOKEN = token_info.get('refresh_token')
    
    # 4. เก็บ Access Token ชั่วคราว เพื่อส่งไปที่ /success
    GLOBAL_ACCESS_TOKEN_CACHE = token_info.get('access_token')
    print("TOKENS RECEIVED:", GLOBAL_ACCESS_TOKEN_CACHE)
    # session['auth_access_token'] = new_access_token
    # token = session.get('auth_access_token')
    # return ออกมาในรูปแบบของ JSON (สำหรับทดสอบ) ในหน้าเว็บเบราว์เซอร์    
    # return jsonify({
    #     "status": "Success! Tokens received.",
    #     "access_token": token_info.get('access_token'),
    #     "refresh_token_stored": bool(GLOBAL_REFRESH_TOKEN),
    #     "next_step": f"ใช้ Access Token นี้หรือเรียก /api/workflow"
    # })
    return redirect(url_for('success_page'))

@app.route('/api/get_token', methods=['GET'])
def get_latest_token_for_workflow():

    global GLOBAL_ACCESS_TOKEN_CACHE
    token = GLOBAL_ACCESS_TOKEN_CACHE
    max_retries = 10
    delay_seconds = 2
    for _ in range(max_retries):
        token = GLOBAL_ACCESS_TOKEN_CACHE
        if token:
            # Token ถูกพบ! ล้างค่าและส่งกลับ
            GLOBAL_ACCESS_TOKEN_CACHE = None 
            return jsonify({
                "access_token": token
            })
        
        # ยังไม่พบ Token, พัก (sleep) ก่อนลองใหม่
        time.sleep(delay_seconds) 
        
    # หากหมดเวลารอ (20 วินาที) แล้วยังไม่พบ
    return jsonify({"error": f"Access Token not found after {max_retries * delay_seconds} seconds. Authorization failed or timed out."}), 404
    

@app.route('/success')
def success_page():
    html_content = """
    <html>
        <body>
            <h1>✅ เชื่อมต่อ Google Calendar สำเร็จ!</h1>
            <p>ระบบได้จัดเก็บสิทธิ์การเข้าถึง (Refresh Token) เรียบร้อยแล้ว</p>
            <p>คุณสามารถปิดหน้าต่างนี้ได้เลย</p>
        </body>
    </html>
    """
    # 💥 สั่งให้ส่ง HTML กลับไปเลย เมื่อเป็น GET
    return render_template_string(html_content)
    
## 3. 🧠 Endpoint ที่ Workflow Engine จะเรียกใช้
# @app.route('/api/workflow', methods=['POST'])
# def workflow_entry():
#     """รับคำขอจาก Workflow Engine และจัดการ LLM/Calendar API"""
    
#     if not GLOBAL_REFRESH_TOKEN:
#         return jsonify({"error": "No Refresh Token. Please run /auth/google first."}), 401

#     # 1. 🔄 Logic: รีเฟรช Access Token ก่อนใช้งาน (OAuth2 Management)
#     access_token = refresh_access_token()
#     if not access_token:
#         return jsonify({"error": "Failed to refresh Access Token. Check CLIENT_SECRET."}), 500

#     # 2. 🧠 Logic: ส่ง Query ไปที่ LLM Node (จำลอง)
#     user_query = request.json.get('query', 'List my next 5 events.')
    
#     # *** นี่คือจุดที่คุณจะเรียก LLM Node ***
#     # LLM_NODE_RESPONSE = call_llm(user_query) 
#     # ** จำลองผลลัพธ์จาก LLM **
#     LLM_NODE_RESPONSE = {
#         "operation": "LIST",
#         "method": "GET",
#         "url": CALENDAR_API_BASE,
#         "payload": {"maxResults": 5, "orderBy": "startTime", "singleEvents": True}
#     }

#     # 3. 🌐 Logic: ยิง HTTP Request ไปที่ Google Calendar API
#     op = LLM_NODE_RESPONSE['operation']
    
#     headers = {'Authorization': f'Bearer {access_token}'}
#     params = LLM_NODE_RESPONSE.get('payload', {}) if op == 'LIST' else {}
#     data = LLM_NODE_RESPONSE.get('payload', {}) if op in ['CREATE', 'UPDATE'] else None

#     # สำหรับการทดสอบ เราจะเรียก LIST
#     calendar_response = requests.request(
#         method=LLM_NODE_RESPONSE['method'],
#         url=LLM_NODE_RESPONSE['url'],
#         headers=headers,
#         params=params,
#         json=data if data else None # ใช้ json=data แทน data=data สำหรับ POST/PUT
#     )

#     return jsonify({
#         "status": "success",
#         "calendar_operation": op,
#         "google_calendar_response": calendar_response.json(),
#         "access_token_used": access_token
#     })

# # ฟังก์ชันรีเฟรชโทเค็น
# def refresh_access_token():
#     """ใช้ Refresh Token เพื่อขอ Access Token ใหม่"""
#     global GLOBAL_REFRESH_TOKEN
    
#     token_data = {
#         'client_id': CLIENT_ID,
#         'client_secret': CLIENT_SECRET,
#         'refresh_token': GLOBAL_REFRESH_TOKEN,
#         'grant_type': 'refresh_token'
#     }
    
#     response = requests.post(TOKEN_ENDPOINT, data=token_data)
#     if response.status_code == 200:
#         return response.json().get('access_token')
    
#     print("TOKEN REFRESH FAILED:", response.json())
#     return None

if __name__ == '__main__':
    print("Backend Server Started.")
    print("-----------------------------------------------------")
    print("ขั้นตอนที่ 1: Start ngrok และแทนที่ 'YOUR_NGROK_URL'")
    print("ขั้นตอนที่ 2: ตั้งค่า Redirect URI ใน Google Cloud Console")
    print("ขั้นตอนที่ 3: ไปที่ http://127.0.0.1:5000/auth/google เพื่อเริ่ม OAuth Flow")
    print("-----------------------------------------------------")
    app.run(debug=True, port=5000)