"""
Smart Body Worn Camera - Camera Manager
Demonstrates: Singleton, multi-threading, mutex, queue-based encoding,
OpenCV capture, FFmpeg H.264 encoding via subprocess pipe.
Key difficulty: single thread cannot handle decode+encode simultaneously;
solution: capture thread pushes frames to queue, encoder thread pulls and writes.
"""
import cv2
import os
import time
import threading
import subprocess as sp
from datetime import datetime
from models import Database

BASE_DIR = os.path.dirname(__file__)
PHOTO_DIR = os.path.join(BASE_DIR, "photos")
VIDEO_DIR = os.path.join(BASE_DIR, "recordings")


class CameraManager:
    """Singleton camera manager with threaded capture and recording."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.cap = None
        self.camera_id = 0
        self.frame_lock = threading.Lock()
        self.latest_frame = None  # shared buffer for MJPEG stream
        self.running = False
        self.capture_thread = None

        # Recording state
        self.recording = False
        self.record_start_time = None
        self.record_filename = ""
        self.ffmpeg_proc = None
        self.frame_queue = []
        self.queue_lock = threading.Lock()
        self.encode_thread = None
        self.stop_encode = False

        # FPS
        self.fps = 25.0
        self.frame_interval = 1.0 / self.fps

    # ── Camera Control ───────────────────────────────────────────────────

    def start_camera(self, camera_id=0):
        if self.running:
            return True
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        # Try default resolution first, fall back
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        if not self.cap.isOpened():
            # Try next camera
            for cid in range(1, 5):
                self.cap = cv2.VideoCapture(cid, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.camera_id = cid
                    break
            if not self.cap.isOpened():
                return False

        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        Database().add_log("camera_start", f"Camera {self.camera_id} started")
        return True

    def stop_camera(self):
        self.running = False
        if self.recording:
            self.stop_recording()
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        if self.cap:
            self.cap.release()
            self.cap = None
        self.latest_frame = None
        Database().add_log("camera_stop", "Camera stopped")

    def _capture_loop(self):
        """Main capture thread: reads frames into shared buffer."""
        last_time = time.time()
        while self.running:
            if self.cap is None:
                break
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            now = time.time()
            if now - last_time < self.frame_interval:
                time.sleep(0.001)
                continue
            last_time = now

            with self.frame_lock:
                self.latest_frame = frame.copy()

            # If recording, push frame to encode queue
            if self.recording:
                with self.queue_lock:
                    self.frame_queue.append(frame.copy())

    def get_latest_frame(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    # ── Photo ────────────────────────────────────────────────────────────

    def take_photo(self):
        frame = self.get_latest_frame()
        if frame is None:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"photo_{timestamp}.jpg"
        path = os.path.join(PHOTO_DIR, filename)
        cv2.imwrite(path, frame)
        Database().add_photo(filename, path)
        Database().add_log("photo_capture", filename)
        return filename

    # ── Recording (H.264 via FFmpeg pipe) ────────────────────────────────

    def start_recording(self):
        if not self.running or self.recording:
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.record_filename = f"video_{timestamp}"
        h264_path = os.path.join(VIDEO_DIR, self.record_filename + ".h264")

        self.record_start_time = time.time()
        self.frame_queue = []
        self.stop_encode = False
        self.recording = True

        # FFmpeg H.264 encoding via stdin pipe
        # Input: raw rgb24 frames piped via stdin
        # Output: H.264 elementary stream
        width, height = 640, 480
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgr24",
            "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            h264_path
        ]

        try:
            self.ffmpeg_proc = sp.Popen(
                ffmpeg_cmd,
                stdin=sp.PIPE,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL
            )
        except FileNotFoundError:
            self.recording = False
            Database().add_log("record_error", "FFmpeg not found")
            return False

        self.encode_thread = threading.Thread(target=self._encode_loop, daemon=True)
        self.encode_thread.start()
        Database().add_log("record_start", self.record_filename)
        return True

    def _encode_loop(self):
        """Encoder thread: pulls frames from queue, writes to FFmpeg stdin."""
        while not self.stop_encode or len(self.frame_queue) > 0:
            if len(self.frame_queue) == 0:
                time.sleep(0.01)
                continue
            with self.queue_lock:
                if len(self.frame_queue) > 0:
                    frame = self.frame_queue.pop(0)
                else:
                    continue
            try:
                if self.ffmpeg_proc and self.ffmpeg_proc.stdin:
                    self.ffmpeg_proc.stdin.write(frame.tobytes())
            except:
                break

        if self.ffmpeg_proc:
            try:
                self.ffmpeg_proc.stdin.close()
            except:
                pass
            self.ffmpeg_proc.wait(timeout=5)
            self.ffmpeg_proc = None

    def stop_recording(self):
        if not self.recording:
            return None
        self.stop_encode = True
        if self.encode_thread:
            self.encode_thread.join(timeout=5)

        duration = time.time() - self.record_start_time if self.record_start_time else 0
        self.recording = False

        h264_path = os.path.join(VIDEO_DIR, self.record_filename + ".h264")
        size = os.path.getsize(h264_path) if os.path.exists(h264_path) else 0

        Database().add_video(self.record_filename + ".h264", h264_path,
                             "h264", round(duration, 1), size)
        Database().add_log("record_stop",
                           f"{self.record_filename} ({round(duration,1)}s, {size}B)")

        result = self.record_filename
        self.record_filename = ""
        return result

    def is_camera_open(self):
        return self.running and self.cap is not None and self.cap.isOpened()

    def is_recording(self):
        return self.recording

    def get_status(self):
        return {
            "camera_open": self.is_camera_open(),
            "recording": self.is_recording(),
            "camera_id": self.camera_id,
            "fps": self.fps,
        }

