from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("INNOVERCE_DB_PATH",
                     ROOT / "data" / "innoverce26.sqlite3"))
HOST = os.environ.get("INNOVERCE_HOST", "127.0.0.1")
PORT = int(os.environ.get("INNOVERCE_PORT", "8000"))
PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 7 * 24 * 60 * 60
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def connect_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    connection = connect_database()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash BLOB PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS event_registrations (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                college TEXT NOT NULL,
                team TEXT NOT NULL,
                team_size INTEGER NOT NULL CHECK (team_size BETWEEN 1 AND 4),
                track TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class InnoverceHandler(SimpleHTTPRequestHandler):
    server_version = "Innoverce26"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"{self.address_string()} - {format_string % args}")

    def send_json(self, status: HTTPStatus, payload: dict[str, object], cookie: str | None = None) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request length.") from error
        if content_length < 0 or content_length > 16_384:
            raise ValueError("Request is too large.")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Send this request as JSON.")
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(
                "Request body must contain valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def cookie_token(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except (ValueError, TypeError):
            return None
        morsel = cookie.get("innoverce26_session")
        return morsel.value if morsel else None

    def current_user(self) -> sqlite3.Row | None:
        token = self.cookie_token()
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode(
            "ascii", errors="ignore")).digest()
        now = int(time.time())
        with database_connection() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (now,))
            return connection.execute(
                """
                SELECT users.id, users.name, users.email
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()

    def make_session_cookie(self, token: str, max_age: int) -> str:
        secure = "; Secure" if self.headers.get(
            "X-Forwarded-Proto", "").lower() == "https" else ""
        return (
            f"innoverce26_session={token}; Path=/; HttpOnly; SameSite=Strict"
            f"; Max-Age={max_age}{secure}"
        )

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/auth.html?mode=login")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/api/session":
            user = self.current_user()
            if user is None:
                self.send_json(HTTPStatus.UNAUTHORIZED, {
                               "error": "Sign in to continue."})
            else:
                self.send_json(HTTPStatus.OK, {
                               "authenticated": True, "user": dict(user)})
            return
        if path == "/api/profile":
            user = self.current_user()
            if user is None:
                self.send_json(HTTPStatus.UNAUTHORIZED, {
                               "error": "Sign in to continue."})
                return
            with database_connection() as connection:
                account = connection.execute(
                    "SELECT name, email, created_at FROM users WHERE id = ?",
                    (user["id"],),
                ).fetchone()
                registration = connection.execute(
                    """
                    SELECT id, name, email, college, team, team_size, track, created_at
                    FROM event_registrations WHERE user_id = ?
                    """,
                    (user["id"],),
                ).fetchone()
            result: dict[str, object] = {"user": dict(account)}
            if registration is not None:
                result["registration"] = {
                    **dict(registration),
                    "passNumber": f"I26{registration['id']:09d}",
                }
            self.send_json(HTTPStatus.OK, result)
            return
        if path == "/api/event-registration":
            user = self.current_user()
            if user is None:
                self.send_json(HTTPStatus.UNAUTHORIZED, {
                               "error": "Sign in to continue."})
                return
            with database_connection() as connection:
                registration = connection.execute(
                    """
                    SELECT id, name, email, college, team, team_size, track
                    FROM event_registrations WHERE user_id = ?
                    """,
                    (user["id"],),
                ).fetchone()
            if registration is None:
                self.send_json(HTTPStatus.NOT_FOUND, {
                               "error": "No boarding pass has been issued."})
            else:
                result = dict(registration)
                result["passNumber"] = f"I26{registration['id']:09d}"
                self.send_json(HTTPStatus.OK, result)
            return
        if path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {
                           "error": "API endpoint not found."})
            return
        decoded = unquote(path)
        if decoded.casefold() == "/orbit24.html" and self.current_user() is None:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/auth.html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        target = Path(self.translate_path(self.path)).resolve()
        data_directory = (ROOT / "data").resolve()
        if (
            data_directory == target
            or data_directory in target.parents
            or decoded.casefold().endswith(".py")
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        handlers = {
            "/api/register": self.register,
            "/api/login": self.login,
            "/api/logout": self.logout,
            "/api/delete-account": self.delete_account,
            "/api/event-registration": self.register_event,
        }
        handler = handlers.get(path)
        if handler is None:
            self.send_json(HTTPStatus.NOT_FOUND, {
                           "error": "API endpoint not found."})
            return
        try:
            payload = self.read_json()
            handler(payload)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except sqlite3.IntegrityError:
            if path == "/api/register":
                self.send_json(HTTPStatus.CONFLICT, {
                               "error": "An account already exists for this email."})
            else:
                self.send_json(HTTPStatus.CONFLICT, {
                               "error": "A boarding pass has already been issued for this account."})
        except sqlite3.Error:
            self.log_error("Database operation failed for %s", path)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                           "error": "Could not save your details. Please try again."})

    def register(self, payload: dict[str, object]) -> None:
        name = self.required_text(payload, "name", "Name", 80)
        email = self.normalized_email(payload)
        password = payload.get("password")
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise ValueError("Password must be between 8 and 128 characters.")
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
        with database_connection() as connection:
            connection.execute(
                "INSERT INTO users (name, email, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, email, salt, password_hash, int(time.time())),
            )
        self.send_json(HTTPStatus.CREATED, {
                       "message": "Account created. Log in with your email and password to continue."})

    def login(self, payload: dict[str, object]) -> None:
        email = self.normalized_email(payload)
        password = payload.get("password")
        if not isinstance(password, str) or not password or len(password) > 128:
            self.send_json(HTTPStatus.UNAUTHORIZED, {
                           "error": "Email or password is incorrect."})
            return
        with database_connection() as connection:
            user = connection.execute(
                "SELECT id, name, email, password_salt, password_hash FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
        if user is None:
            self.send_json(HTTPStatus.UNAUTHORIZED, {
                           "error": "Email or password is incorrect."})
            return
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(
                "utf-8"), user["password_salt"], PASSWORD_ITERATIONS
        )
        if not hmac.compare_digest(candidate, user["password_hash"]):
            self.send_json(HTTPStatus.UNAUTHORIZED, {
                           "error": "Email or password is incorrect."})
            return

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_SECONDS
        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        with database_connection() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user["id"], expires_at),
            )
        self.send_json(
            HTTPStatus.OK,
            {"authenticated": True},
            self.make_session_cookie(token, SESSION_SECONDS),
        )

    def logout(self, _payload: dict[str, object]) -> None:
        token = self.cookie_token()
        if token:
            token_hash = hashlib.sha256(token.encode(
                "ascii", errors="ignore")).digest()
            with database_connection() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        self.send_json(
            HTTPStatus.OK,
            {"message": "Signed out."},
            "innoverce26_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )

    def delete_account(self, payload: dict[str, object]) -> None:
        user = self.current_user()
        if user is None:
            self.send_json(HTTPStatus.UNAUTHORIZED, {
                           "error": "Your session has expired. Please log in again."})
            return
        password = payload.get("password")
        confirmation = payload.get("confirmation")
        if confirmation != "DELETE":
            raise ValueError("Type DELETE to confirm account removal.")
        if not isinstance(password, str) or not password or len(password) > 128:
            raise ValueError("Enter your password to delete your account.")
        with database_connection() as connection:
            account = connection.execute(
                "SELECT password_salt, password_hash FROM users WHERE id = ?",
                (user["id"],),
            ).fetchone()
            if account is None:
                self.send_json(HTTPStatus.UNAUTHORIZED, {
                               "error": "Your account could not be found."})
                return
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), account["password_salt"],
                PASSWORD_ITERATIONS,
            )
            if not hmac.compare_digest(candidate, account["password_hash"]):
                self.send_json(HTTPStatus.UNAUTHORIZED, {
                               "error": "Password is incorrect. Your account was not deleted."})
                return
            connection.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        self.send_json(
            HTTPStatus.OK,
            {"message": "Your account and registration details have been deleted."},
            "innoverce26_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )

    def register_event(self, payload: dict[str, object]) -> None:
        user = self.current_user()
        if user is None:
            self.send_json(HTTPStatus.UNAUTHORIZED, {
                           "error": "Your session has expired. Please log in again."})
            return
        name = self.required_text(payload, "name", "Name", 80)
        email = self.normalized_email(payload)
        college = self.required_text(payload, "college", "College", 160)
        team = self.required_text(payload, "team", "Team name", 80)
        raw_size = payload.get("size")
        if isinstance(raw_size, bool) or not isinstance(raw_size, (str, int)):
            raise ValueError("Team size must be between 1 and 4.")
        try:
            team_size = int(raw_size)
        except (TypeError, ValueError) as error:
            raise ValueError("Team size must be between 1 and 4.") from error
        if team_size < 1 or team_size > 4:
            raise ValueError("Team size must be between 1 and 4.")
        track = self.required_text(payload, "track", "Track", 40)
        if email.casefold() != str(user["email"]).casefold():
            raise ValueError(
                "Use the email address associated with your account.")
        with database_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO event_registrations
                    (user_id, name, email, college, team, team_size, track, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user["id"], name, user["email"], college,
                 team, team_size, track, int(time.time())),
            )
            pass_number = f"I26{cursor.lastrowid:09d}"
        self.send_json(HTTPStatus.CREATED, {"passNumber": pass_number})

    @staticmethod
    def required_text(payload: dict[str, object], key: str, label: str, maximum: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(
                f"{label} is required and must be no longer than {maximum} characters.")
        return value.strip()

    def normalized_email(self, payload: dict[str, object]) -> str:
        email = self.required_text(payload, "email", "Email", 254).lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email

    def translate_path(self, path: str) -> str:
        translated = Path(super().translate_path(path)).resolve()
        if translated != ROOT and ROOT not in translated.parents:
            return str(ROOT / "__not_found__")
        return str(translated)


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), InnoverceHandler)
    print(
        f"Innoverce 26 login page: http://{HOST}:{PORT}/auth.html?mode=login")
    print(f"SQLite database: {DATABASE_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Innoverce 26.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
