"""Shared fixtures. Run from the project folder with:  pip install pytest  &&  pytest -q"""
import functools
import http.server
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(scope="session")
def media_site(tmp_path_factory):
    """A tiny local web server with a 2-second test clip, so download tests need no internet."""
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg is not installed")
    root = tmp_path_factory.mktemp("site")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25", "-f", "lavfi",
         "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(root / "clip.mp4")], check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    (root / "page.html").write_text(
        f'<html><head><title>Test Page</title></head><body>'
        f'<a href="x">x</a> <script>var a = "{base}/clip.mp4"; var b = "{base}/stream/index.m3u8";</script>'
        f'</body></html>', encoding="utf-8")
    yield {"base": base, "root": root}
    srv.shutdown()


@pytest.fixture(autouse=True)
def local_traffic_never_uses_a_proxy(monkeypatch):
    """A developer machine may have a system or environment proxy; the local test servers must not go through it."""
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


@pytest.fixture(scope="session")
def html_site(tmp_path_factory):
    """A local web server with one plain HTML page (no ffmpeg needed)."""
    root = tmp_path_factory.mktemp("html")
    (root / "page.html").write_text("<html><head><title>Proxied page</title></head><body>hello</body></html>", encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"port": srv.server_port}
    srv.shutdown()


@pytest.fixture
def http_proxy(html_site):
    """A minimal HTTP proxy: answers every absolute-URI request with the test page and remembers what was asked."""
    seen = []
    body = b"<html><head><title>Proxied page</title></head></html>"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()


@pytest.fixture
def socks5_proxy(html_site):
    """A minimal SOCKS5 server (no authentication). It ignores the requested host and connects to the local test page."""
    seen = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)

    def pipe(src, dst):
        try:
            while (data := src.recv(65536)):
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def client(conn):
        try:
            conn.recv(262)                                   # greeting
            conn.sendall(b"\x05\x00")                        # no authentication
            head = conn.recv(4)                              # VER CMD RSV ATYP
            if head[3] == 1:
                host = socket.inet_ntoa(conn.recv(4))
            elif head[3] == 3:
                host = conn.recv(conn.recv(1)[0]).decode()
            else:
                return
            port = int.from_bytes(conn.recv(2), "big")
            seen.append((host, port))
            upstream = socket.create_connection(("127.0.0.1", html_site["port"]))
            conn.sendall(b"\x05\x00\x00\x01" + bytes(6))
            threading.Thread(target=pipe, args=(conn, upstream), daemon=True).start()
            pipe(upstream, conn)
        except OSError:
            pass

    def accept():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=client, args=(conn,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    yield f"socks5h://127.0.0.1:{listener.getsockname()[1]}", seen
    listener.close()
