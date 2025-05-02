import cv2
import threading
import time
from flask import Flask, Response, render_template, jsonify

app = Flask(__name__)

# Biến toàn cục lưu frame mới nhất từ webcam
latest_frame = None
zoom_factor = 1.0  # Mặc định không zoom

# Luồng lấy ảnh liên tục từ webcam
def capture_frames():
    global latest_frame
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        raise RuntimeError("Không thể mở webcam.")

    while True:
        success, frame = cap.read()
        if success:
            latest_frame = frame
        time.sleep(0.01)

# Hàm zoom ảnh
def zoom_image(image, zoom=1.0):
    if zoom == 1.0:
        return image
    h, w = image.shape[:2]
    center_x, center_y = w // 2, h // 2
    radius_x, radius_y = int(w / (2 * zoom)), int(h / (2 * zoom))

    cropped = image[center_y - radius_y:center_y + radius_y,
                    center_x - radius_x:center_x + radius_x]
    return cv2.resize(cropped, (w, h))

# Stream video qua Flask
def generate_frames():
    global latest_frame, zoom_factor
    while True:
        if latest_frame is None:
            continue
        frame = zoom_image(latest_frame.copy(), zoom=zoom_factor)
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# 📸 API chụp ảnh
@app.route('/capture', methods=['GET'])
def capture_image():
    global latest_frame
    if latest_frame is not None:
        timestamp = int(time.time())
        filename = f"capture_{timestamp}.jpg"
        cv2.imwrite(filename, latest_frame)
        return jsonify({"message": "Ảnh đã được lưu", "file": filename})
    return jsonify({"error": "Chưa có frame để lưu"}), 500

# 🔍 API thu phóng
@app.route('/zoom/<float:factor>', methods=['POST'])
def set_zoom(factor):
    global zoom_factor
    zoom_factor = max(1.0, min(factor, 4.0))  # Giới hạn zoom từ 1x đến 4x
    return jsonify({"zoom_factor": zoom_factor})

if __name__ == '__main__':
    threading.Thread(target=capture_frames, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
