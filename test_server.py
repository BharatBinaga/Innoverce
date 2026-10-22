import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), server.InnoverceHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        server.DATABASE_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        server.initialize_database()
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def request(self, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers)
        try:
            response = self.client.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_account_registration_login_event_and_logout(self) -> None:
        login_page = self.client.open(self.base_url + "/")
        self.assertTrue(login_page.geturl().endswith("/auth.html?mode=login"))
        protected_page = self.client.open(self.base_url + "/Orbit24.html")
        self.assertTrue(protected_page.geturl().endswith("/auth.html"))
        self.assertEqual(
            self.request(
                "/api/register",
                {"name": "Aarav Gowda", "email": "aarav@example.edu",
                    "password": "safe-pass-123"},
            )[0],
            201,
        )
        self.assertEqual(self.request("/api/session")[0], 401)
        self.assertEqual(
            self.request(
                "/api/login", {"email": "aarav@example.edu", "password": "wrong-pass"})[0],
            401,
        )
        self.assertEqual(
            self.request(
                "/api/login", {"email": "aarav@example.edu", "password": "safe-pass-123"})[0],
            200,
        )
        protected_page = self.client.open(self.base_url + "/Orbit24.html")
        self.assertTrue(protected_page.geturl().endswith("/Orbit24.html"))
        session_status, session = self.request("/api/session")
        self.assertEqual(session_status, 200)
        user = session.get("user")
        self.assertIsInstance(user, dict)
        self.assertEqual(user.get("email"), "aarav@example.edu")

        event = {
            "name": "Aarav Gowda",
            "email": "aarav@example.edu",
            "college": "Example College",
            "team": "Null Pointers",
            "size": "4",
            "track": "Signal",
        }
        status, ticket = self.request("/api/event-registration", event)
        self.assertEqual(status, 201)
        pass_number = ticket.get("passNumber")
        self.assertIsInstance(pass_number, str)
        self.assertRegex(pass_number, r"^I26\d{9}$")
        saved_status, saved_ticket = self.request("/api/event-registration")
        self.assertEqual(saved_status, 200)
        self.assertEqual(saved_ticket.get("passNumber"), pass_number)
        self.assertEqual(self.request(
            "/api/event-registration", event)[0], 409)
        with server.database_connection() as connection:
            saved = connection.execute(
                "SELECT name, email, college, team, team_size, track FROM event_registrations"
            ).fetchone()
        self.assertEqual(tuple(saved), ("Aarav Gowda", "aarav@example.edu",
                         "Example College", "Null Pointers", 4, "Signal"))

        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/session")[0], 401)

    def test_account_validation_and_duplicate_email(self) -> None:
        invalid_status, invalid_result = self.request(
            "/api/register", {"name": "Crew",
                              "email": "not-an-email", "password": "safe-pass-123"}
        )
        self.assertEqual(invalid_status, 400)
        error_message = invalid_result.get("error")
        self.assertIsInstance(error_message, str)
        self.assertIn("valid email", error_message)
        payload = {"name": "Crew", "email": "crew@example.edu",
                   "password": "safe-pass-123"}
        self.assertEqual(self.request("/api/register", payload)[0], 201)
        payload["email"] = "CREW@example.edu"
        self.assertEqual(self.request("/api/register", payload)[0], 409)

    def test_profile_and_account_deletion_require_reauthentication(self) -> None:
        self.assertEqual(
            self.request(
                "/api/register",
                {"name": "Crew", "email": "crew@example.edu",
                    "password": "safe-pass-123"},
            )[0],
            201,
        )
        self.assertEqual(
            self.request(
                "/api/login",
                {"email": "crew@example.edu", "password": "safe-pass-123"},
            )[0],
            200,
        )
        profile_status, profile = self.request("/api/profile")
        self.assertEqual(profile_status, 200)
        user = profile.get("user")
        self.assertIsInstance(user, dict)
        self.assertEqual(user.get("name"), "Crew")
        self.assertIsInstance(user.get("created_at"), int)

        self.assertEqual(
            self.request(
                "/api/delete-account",
                {"password": "incorrect-password", "confirmation": "DELETE"},
            )[0],
            401,
        )
        self.assertEqual(self.request("/api/profile")[0], 200)
        self.assertEqual(
            self.request(
                "/api/delete-account",
                {"password": "safe-pass-123", "confirmation": "not-confirmed"},
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "/api/delete-account",
                {"password": "safe-pass-123", "confirmation": "DELETE"},
            )[0],
            200,
        )
        self.assertEqual(self.request("/api/profile")[0], 401)
        with server.database_connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM event_registrations").fetchone()[0], 0
            )


if __name__ == "__main__":
    unittest.main()
