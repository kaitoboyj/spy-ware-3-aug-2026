import socketio
import mss
import time
import socket
import platform
import base64
import io
import psutil
from PIL import Image

# --- CONFIGURATION ---
# Replace with your computer's IP address (e.g., "http://192.168.1.15:5000")
SERVER_URL = "http://localhost:5000" 
# ---------------------

sio = socketio.Client()

def get_system_info():
    try:
        ram = round(psutil.virtual_memory().total / (1024**3), 1)
    except:
        ram = "Unknown"
    return f"{platform.system()} {platform.release()} | {ram}GB RAM"

@sio.event
def connect():
    print("Connected to Dashboard Server")
    try:
        ip_addr = socket.gethostbyname(socket.gethostname())
    except:
        ip_addr = "Unknown"
    sio.emit('register', {
        'name': socket.gethostname(),
        'ip': ip_addr,
        'specs': get_system_info()
    })

def stream_screen():
    with mss.mss() as sct:
        while True:
            if sio.connected:
                try:
                    # Capture the primary monitor
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    
                    # Convert to Image and resize for smooth streaming
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    img.thumbnail((800, 450)) # Maintains aspect ratio
                    
                    # Compress to JPEG
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=40)
                    frame_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    sio.emit('screen_frame', {'frame': frame_b64})
                except Exception as e:
                    print(f"Streaming error: {e}")
            
            time.sleep(0.5) # Stream at ~2 frames per second

if __name__ == '__main__':
    while True:
        try:
            if not sio.connected:
                print(f"Attempting to connect to {SERVER_URL}...")
                sio.connect(SERVER_URL)
            stream_screen()
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
