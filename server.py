"""Local preview and membership-request receiver for Workout Gym."""

import argparse
import json
import re
import sqlite3
import uuid
from contextlib import closing
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PAGES = {"/", "/index.html", "/uyelik", "/uyelik/", "/salon", "/salon/"}
SCRIPTS = {"/style.css", "/site.js", "/translations.js"}
ASSETS = {"/assets/" + name for name in (
    "altin-heykel.webp", "circir-salon.webp", "kurucu-portre.webp",
    "workout-gym-dis-cephe.webp", "salon-turu.mp4",
)}
BRANCHES = {"caglayan", "circir", "ornektepe"}
PLANS = {"", "3+3", "6+6"}
LANGUAGES = {"tr", "en", "ar"}
PHONE_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def validate(data):
    def read(key):
        value = data.get(key)
        return value.strip() if isinstance(value, str) else ""

    name = read("name")
    phone = read("phone").translate(PHONE_DIGITS)
    email = read("email")
    branch = read("branch")
    plan = read("plan")
    language = read("language")
    digits = re.sub(r"[^0-9]", "", phone)
    errors = {}

    if not 2 <= len(name) <= 100 or not name.isprintable():
        errors["name"] = "errorName"
    if not re.fullmatch(r"\+?[0-9 ().-]{1,35}", phone) or not 10 <= len(digits) <= 15:
        errors["phone"] = "errorPhone"
    if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+", email)):
        errors["email"] = "errorEmail"
    if branch not in BRANCHES:
        errors["branch"] = "errorBranch"
    if plan not in PLANS or (plan and branch != "circir"):
        errors["plan"] = "errorPlan"
    if data.get("consent") is not True:
        errors["consent"] = "errorConsent"

    return errors, (
        name, ("+" if phone.startswith("+") else "") + digits,
        email, branch, plan, language if language in LANGUAGES else "tr",
    )


class SiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **options):
        super().__init__(*args, directory=ROOT, **options)

    def send_head(self):
        path = urlsplit(self.path).path
        if path in PAGES:
            self.path = "/index.html"
        elif path not in SCRIPTS and path not in ASSETS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None

        if path == "/assets/salon-turu.mp4":
            return self.send_video()
        return super().send_head()

    def send_video(self):
        video_path = ROOT / "assets" / "salon-turu.mp4"
        try:
            video = video_path.open("rb")
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None

        size = video_path.stat().st_size
        start, end, status = 0, size - 1, HTTPStatus.OK
        specified = self.headers.get("Range")
        if specified:
            match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", specified)
            if match and match.group(1):
                start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), end)
            elif match and match.group(2):
                start = max(size - int(match.group(2)), 0)
            else:
                start = size
            if start >= size or start > end:
                video.close()
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            status = HTTPStatus.PARTIAL_CONTENT

        self.video_bytes_remaining = end - start + 1
        video.seek(start)
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(self.video_bytes_remaining))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        return video

    def copyfile(self, source, output):
        if not hasattr(self, "video_bytes_remaining"):
            return super().copyfile(source, output)
        try:
            while self.video_bytes_remaining:
                chunk = source.read(min(self.video_bytes_remaining, 256 * 1024))
                if not chunk:
                    break
                output.write(chunk)
                self.video_bytes_remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/leads":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "json_required"})
            return

        size = self.headers.get("Content-Length", "")
        if not re.fullmatch(r"[0-9]{1,4}", size) or not 1 <= int(size) <= 8192:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"})
            return
        try:
            data = json.loads(self.rfile.read(int(size)))
            if not isinstance(data, dict) or not isinstance(data.get("requestId"), str):
                raise ValueError
            request_id = uuid.UUID(data["requestId"])
            if request_id.version != 4:
                raise ValueError
        except (ValueError, UnicodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return

        errors, lead = validate(data)
        if errors:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"errors": errors})
            return

        try:
            with closing(sqlite3.connect(self.server.database)) as connection, connection:
                saved = connection.execute(
                    "SELECT name, phone, email, branch, plan FROM leads WHERE request_id = ?",
                    (request_id.hex,),
                ).fetchone()
                if saved is None:
                    connection.execute(
                        """INSERT INTO leads (request_id, name, phone, email, branch, plan, language)
                        VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_id) DO NOTHING""",
                        (request_id.hex, *lead),
                    )
                    saved = connection.execute(
                        "SELECT name, phone, email, branch, plan FROM leads WHERE request_id = ?",
                        (request_id.hex,),
                    ).fetchone()
            if saved != lead[:5]:
                self.send_json(HTTPStatus.CONFLICT, {"error": "request_conflict"})
                return
        except sqlite3.Error:
            self.log_error("Could not store membership request.")
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "storage_unavailable"})
            return

        self.send_json(HTTPStatus.CREATED, {"reference": request_id.hex[:8].upper()})


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8849)
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "leads.sqlite3")
    options = parser.parse_args()

    options.database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(options.database)) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS leads (
                request_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                branch TEXT NOT NULL,
                plan TEXT NOT NULL,
                language TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )

    with ThreadingHTTPServer((options.host, options.port), SiteHandler) as server:
        server.database = options.database
        print(f"Workout Gym at http://{options.host}:{options.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    run()
