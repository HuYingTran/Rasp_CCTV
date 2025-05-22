from picamera2 import Picamera2
import cv2

import threading
import os
import sys
import time
from datetime import datetime
from flask import Flask, Response, render_template, jsonify, send_from_directory

UPLOAD_FOLDER = 'files'

app = Flask(__name__)

camera_enabled = True
latest_frame = None
frame_lock = threading.Lock()
zoom_factor = 1.0

is_recording = False
video_writer = None
video_filename = None

picam2 = Picamera2()
picam2.preview_configuration.main.size = (320, 240)
picam2.preview_configuration.main.format = "YUV420"
picam2.configure("preview")
picam2.start()

def capture_frames():
    global latest_frame, is_recording, video_writer, video_filename
    while True:
        if camera_enabled:
            frame = picam2.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
            with frame_lock:
                latest_frame = frame.copy()

            if is_recording and video_writer is not None:
                video_writer.write(frame)
        else:
            print("Camera off.")
        time.sleep(0.03)  # giảm tải CPU

def zoom_image(image, zoom=1.0):
    if zoom == 1.0:
        return image
    h, w = image.shape[:2]
    center_x, center_y = w // 2, h // 2
    radius_x, radius_y = int(w / (2 * zoom)), int(h / (2 * zoom))

    # Giới hạn crop
    x1 = max(center_x - radius_x, 0)
    x2 = min(center_x + radius_x, w)
    y1 = max(center_y - radius_y, 0)
    y2 = min(center_y + radius_y, h)

    cropped = image[y1:y2, x1:x2]
    return cv2.resize(cropped, (w, h))

def generate_frames():
    global zoom_factor
    while True:
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.05)
                continue
            frame = latest_frame.copy()

        frame = zoom_image(frame, zoom=zoom_factor)
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' +
               buffer.tobytes() + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# API chup anh
@app.route('/capture', methods=['GET'])
def capture_image():
    with frame_lock:
        if latest_frame is not None:
            timestamp = datetime.now().strftime("%y-%m-%d_%H-%M-%S")
            filename = f"capture_{timestamp}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            cv2.imwrite(filepath, latest_frame)
            return jsonify({
                "message": "Ảnh đã được lưu",
                "file": filename,
                "url": f"/files/{filename}"
            })
    return jsonify({"error": "Chưa có frame để lưu"}), 500

@app.route('/zoom/<float:factor>', methods=['POST'])
def set_zoom(factor):
    global zoom_factor
    zoom_factor = max(1.0, min(factor, 4.0))  # Giới hạn 1x - 4x
    return jsonify({"zoom_factor": zoom_factor})

# API on/off camera
@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    global camera_enabled
    camera_enabled = not camera_enabled
    return jsonify({
        "camera_enabled": camera_enabled,
        "message": "Camera đã {}".format("bật" if camera_enabled else "tắt")
    })

@app.route('/start_record', methods=['POST'])
def start_record():
    global is_recording, video_writer, video_filename

    if is_recording:
        return jsonify({"message": "Đang quay rồi."})

    timestamp = time.strftime("%y-%m-%d_%H-%M-%S")
    video_filename = f"video_{timestamp}.mp4"
    video_path = os.path.join(UPLOAD_FOLDER, video_filename)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 20.0

    # Lấy frame thực để xác định kích thước chính xác
    frame = picam2.capture_array()
    frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
    frame_size = (frame.shape[1], frame.shape[0])

    video_writer = cv2.VideoWriter(video_path, fourcc, fps, frame_size)
    is_recording = True

    return jsonify({"message": f"Bắt đầu quay video: {video_filename}"})

@app.route('/stop_record', methods=['POST'])
def stop_record():
    global is_recording, video_writer, video_filename

    if not is_recording:
        return jsonify({"message": "Không có video nào đang quay."})

    is_recording = False
    if video_writer:
        video_writer.release()
        video_writer = None

    return jsonify({"message": f"Video đã được lưu: {video_filename}", "file": video_filename})

# ROUTER

@app.route('/')
def index():
    return render_template('home.html')


@app.route('/history')
def history():
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    # Lọc file .mp4 và .jpg
    files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(('.mp4', '.jpg'))]
    # Sắp xếp theo ngày tạo mới nhất (mtime)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x)), reverse=True)

    return render_template('explorer.html', files=files)

@app.route('/download/<filename>')
def download_file(filename):
    # Trả về file cho người dùng tải xuống
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    

if __name__ == '__main__':
    threading.Thread(target=capture_frames, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
