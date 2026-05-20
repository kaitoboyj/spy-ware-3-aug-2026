from flask import Flask, render_template, send_file, request
from flask_socketio import SocketIO, emit
from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'charity-monitor-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Supabase Setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "YOUR_SUPABASE_PROJECT_URL":
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase connected successfully")
    except Exception as e:
        print(f"Supabase connection failed: {e}")

# Storage for connected devices
devices = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download_client')
def download_client():
    return send_file(os.path.join('dist', 'client.exe'), as_attachment=True)

@socketio.on('register')
def handle_register(data):
    device_id = request.sid
    hostname = data.get('name')
    
    # Default nickname
    nickname = data.get('nickname', 'New Device')
    
    # Check Supabase for existing nickname if available
    if supabase:
        try:
            response = supabase.table('devices').select('nickname').eq('hostname', hostname).execute()
            if response.data:
                nickname = response.data[0]['nickname']
            else:
                # Insert new device entry
                supabase.table('devices').insert({
                    'hostname': hostname,
                    'nickname': nickname,
                    'ip': data.get('ip'),
                    'specs': data.get('specs')
                }).execute()
        except Exception as e:
            print(f"Supabase error during register: {e}")

    devices[device_id] = {
        'name': hostname,
        'ip': data.get('ip'),
        'nickname': nickname,
        'specs': data.get('specs')
    }
    print(f"Device connected: {hostname} (Nickname: {nickname})")
    emit('update_device_list', devices, broadcast=True)

@socketio.on('screen_frame')
def handle_frame(data):
    device_id = request.sid
    if device_id in devices:
        emit('display_frame', {
            'device_id': device_id,
            'frame': data['frame']
        }, broadcast=True)

@socketio.on('recording_progress')
def handle_recording_progress(data):
    device_id = request.sid
    emit('update_countdown', {
        'device_id': device_id,
        'remaining': data['remaining']
    }, broadcast=True)

@socketio.on('request_screenshot_telegram')
def handle_screenshot_request(data):
    target_id = data.get('device_id')
    if target_id in devices:
        print(f"Requesting screenshot upload for device: {devices[target_id]['name']}")
        emit('force_screenshot', {}, room=target_id)

@socketio.on('request_video_upload')
def handle_video_upload_request(data):
    target_id = data.get('device_id')
    if target_id in devices:
        print(f"Forcing video upload for device: {devices[target_id]['name']}")
        emit('force_upload', {}, room=target_id)

@socketio.on('update_nickname')
def handle_nickname(data):
    target_id = data.get('device_id')
    new_name = data.get('nickname')
    
    if target_id in devices:
        hostname = devices[target_id]['name']
        devices[target_id]['nickname'] = new_name
        
        # Persist to Supabase
        if supabase:
            try:
                supabase.table('devices').update({'nickname': new_name}).eq('hostname', hostname).execute()
            except Exception as e:
                print(f"Supabase error during nickname update: {e}")
                
        emit('update_device_list', devices, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in devices:
        print(f"Device disconnected: {devices[request.sid]['name']}")
        del devices[request.sid]
        emit('update_device_list', devices, broadcast=True)

if __name__ == '__main__':
    # host='0.0.0.0' allows other computers on your network to connect
    socketio.run(app, host='0.0.0.0', port=5000)

