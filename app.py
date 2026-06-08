"""
Smart Body Worn Camera - Flask Web Application
"""
from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, Response, send_file)
from functools import wraps
import cv2
import os
from models import Database
from camera_manager import CameraManager
from transcoder import Transcoder

app = Flask(__name__)
app.secret_key = "bodycam-secret-2026"

db = Database()
cam = CameraManager()

VIDEO_DIR = os.path.join(os.path.dirname(__file__), "recordings")
PHOTO_DIR = os.path.join(os.path.dirname(__file__), "photos")

# ── Auth ─────────────────────────────────────────────────────────────────────

def api_login_required(f):
    """API decorator: returns JSON error instead of redirecting."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "未登录","code":"AUTH"}), 401
        return f(*args, **kwargs)
    return decorated

# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("live_page"))
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/live")
def live_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    return render_template("live.html", username=session.get("user"))

@app.route("/photos")
def photos_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    return render_template("photos.html", username=session.get("user"))

@app.route("/videos")
def videos_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    return render_template("videos.html", username=session.get("user"))

@app.route("/logs")
def logs_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    return render_template("logs.html", username=session.get("user"))

# ── Auth API ─────────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    user = db.authenticate(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401
    session["user"] = user["username"]
    session["role"] = user["role"]
    db.add_log("login", user["username"])
    return jsonify({"ok": True, "username": user["username"]})

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    ok, msg = db.add_user(data.get("username", ""), data.get("password", ""),
                          data.get("realName", ""))
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "message": msg})

@app.route("/api/logout")
def api_logout():
    db.add_log("logout", session.get("user", ""))
    session.clear()
    return redirect(url_for("login_page"))

# ── Camera API ───────────────────────────────────────────────────────────────

@app.route("/api/camera/status")
@api_login_required
def api_camera_status():
    return jsonify(cam.get_status())

@app.route("/api/camera/start", methods=["POST"])
@api_login_required
def api_camera_start():
    cid = request.get_json().get("camera_id", 0)
    ok = cam.start_camera(cid)
    return jsonify({"ok": ok})

@app.route("/api/camera/stop", methods=["POST"])
@api_login_required
def api_camera_stop():
    cam.stop_camera()
    return jsonify({"ok": True})

@app.route("/api/camera/photo", methods=["POST"])
@api_login_required
def api_take_photo():
    filename = cam.take_photo()
    if not filename:
        return jsonify({"error": "摄像头未启动"}), 400
    return jsonify({"ok": True, "filename": filename})

@app.route("/api/camera/record/start", methods=["POST"])
@api_login_required
def api_record_start():
    ok = cam.start_recording()
    return jsonify({"ok": ok})

@app.route("/api/camera/record/stop", methods=["POST"])
@api_login_required
def api_record_stop():
    result = cam.stop_recording()
    return jsonify({"ok": True, "filename": result})

# ── MJPEG Stream ─────────────────────────────────────────────────────────────

def generate_frames():
    import numpy as np
    while cam.running or True:
        frame = cam.get_latest_frame()
        if frame is None:
            blank = np.ones((480, 640, 3), dtype=np.uint8) * 40
            cv2.putText(blank, "No Camera Signal", (150, 250),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)
            ret, jpeg = cv2.imencode(".jpg", blank)
        else:
            if cam.is_recording():
                cv2.circle(frame, (15, 15), 8, (0, 0, 255), -1)
                cv2.putText(frame, "REC", (30, 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            ret, jpeg = cv2.imencode(".jpg", frame,
                                     [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ret:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n"
                   + jpeg.tobytes() + b"\r\n")
        if not cam.running and cam.latest_frame is None:
            import time; time.sleep(0.5)

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ── Photos API ───────────────────────────────────────────────────────────────

@app.route("/api/photos")
@api_login_required
def api_photos():
    photos = db.get_photos()
    result = []
    for p in photos:
        result.append({
            "id": p["id"], "filename": p["filename"],
            "created_at": p["created_at"],
            "url": f"/photo_file/{p['filename']}"
        })
    return jsonify(result)

@app.route("/photo_file/<filename>")
def serve_photo(filename):
    path = os.path.join(PHOTO_DIR, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    return jsonify({"error": "not found"}), 404

# ── Videos API ───────────────────────────────────────────────────────────────

@app.route("/api/videos")
@api_login_required
def api_videos():
    videos = db.get_videos()
    result = []
    for v in videos:
        result.append({
            "id": v["id"], "filename": v["filename"],
            "format": v["format"], "duration": v["duration"],
            "size": v["size"], "created_at": v["created_at"],
            "url": f"/video_file/{v['filename']}"
        })
    return jsonify(result)

@app.route("/video_file/<filename>")
def serve_video(filename):
    path = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(path):
        if filename.endswith(".mp4"):
            mt = "video/mp4"
        elif filename.endswith(".flv"):
            mt = "video/x-flv"
        elif filename.endswith(".avi"):
            mt = "video/x-msvideo"
        else:
            mt = "video/h264"
        return send_file(path, mimetype=mt)
    return jsonify({"error": "not found"}), 404

# ── Transcode API ────────────────────────────────────────────────────────────

@app.route("/api/videos/<int:vid>/transcode", methods=["POST"])
@api_login_required
def api_transcode(vid):
    data = request.get_json()
    fmt = data.get("format", "mp4")
    video = db.get_video_by_id(vid)
    if not video:
        return jsonify({"error": "视频不存在"}), 404
    input_path = video["path"]
    if not os.path.exists(input_path):
        return jsonify({"error": "源文件不存在"}), 404
    output_path = Transcoder.transcode(input_path, fmt)
    if not output_path:
        return jsonify({"error": "转码失败，请检查 FFmpeg"}), 500
    return jsonify({
        "ok": True,
        "output": os.path.basename(output_path),
        "url": f"/video_file/{os.path.basename(output_path)}"
    })

# ── Logs API ─────────────────────────────────────────────────────────────────

@app.route("/api/logs")
@api_login_required
def api_logs():
    logs = db.get_logs(200)
    result = [{"id": l["id"], "action": l["action"], "detail": l["detail"],
               "created_at": l["created_at"]} for l in logs]
    return jsonify(result)

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    app.run(host="127.0.0.1", port=5002, debug=False, threaded=True)
