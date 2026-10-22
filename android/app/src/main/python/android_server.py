import importlib.util
import os
import sys
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer


_server = None
_server_thread = None
_server_lock = threading.Lock()


def start_server(site_directory, data_directory, port):
    global _server, _server_thread

    with _server_lock:
        if _server is not None and _server_thread is not None and _server_thread.is_alive():
            return _server.server_address[1]

        site_path = Path(site_directory).resolve()
        os.environ["INNOVERCE_HOST"] = "127.0.0.1"
        os.environ["INNOVERCE_PORT"] = str(port)
        os.environ["INNOVERCE_DB_PATH"] = str(
            Path(data_directory).resolve() / "innoverce26.sqlite3"
        )
        sys.path.insert(0, str(site_path))

        server_path = site_path / "server.py"
        spec = importlib.util.spec_from_file_location(
            "innoverce26_site_server", server_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("The bundled Python service could not be loaded.")
        site_server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(site_server)
        site_server.initialize_database()
        _server = ThreadingHTTPServer(
            ("127.0.0.1", int(port)), site_server.InnoverceHandler
        )
        _server.daemon_threads = True
        _server_thread = threading.Thread(
            target=_server.serve_forever,
            name="innoverce-local-server",
            daemon=True,
        )
        _server_thread.start()
        return _server.server_address[1]
