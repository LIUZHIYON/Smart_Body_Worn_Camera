"""
Smart Body Worn Camera - Video Transcoder
Demonstrates: FFmpeg subprocess, format conversion (H.264 -> MP4/AVI/FLV)
"""
import subprocess as sp
import os
from models import Database

VIDEO_DIR = os.path.join(os.path.dirname(__file__), "recordings")


class Transcoder:
    """Handles video format conversion via FFmpeg CLI."""

    SUPPORTED_FORMATS = {
        "mp4":  ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart"],
        "avi":  ["-c:v", "libx264", "-c:a", "mp3"],
        "flv":  ["-c:v", "libx264", "-c:a", "aac"],
    }

    @staticmethod
    def transcode(input_path, output_format):
        """Convert H.264 to target format. Returns output path or None."""
        if output_format not in Transcoder.SUPPORTED_FORMATS:
            return None

        base = os.path.splitext(input_path)[0]
        output_path = f"{base}.{output_format}"

        # If output exists, return it
        if os.path.exists(output_path):
            return output_path

        cmd = ["ffmpeg", "-y", "-i", input_path]
        cmd += Transcoder.SUPPORTED_FORMATS[output_format]
        cmd.append(output_path)

        try:
            sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=120)
        except (FileNotFoundError, sp.TimeoutExpired):
            return None

        if os.path.exists(output_path):
            Database().add_log("transcode",
                               f"{os.path.basename(input_path)} -> {output_format}")
            return output_path
        return None

    @staticmethod
    def get_transcoded_path(input_path, output_format):
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}.{output_format}"
        return output_path if os.path.exists(output_path) else None
