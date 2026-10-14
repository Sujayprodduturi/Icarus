from __future__ import annotations

import argparse
import select
import socket
import socketserver
from collections.abc import Sequence

ALLOWED_HOST = "api.kite.trade"
ALLOWED_PORT = 443


def proxy_decision(method: str, target: str) -> tuple[str, int] | None:
    if method != "CONNECT" or target != f"{ALLOWED_HOST}:{ALLOWED_PORT}":
        return None
    return ALLOWED_HOST, ALLOWED_PORT


class _TunnelHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(10)
        line = self.rfile.readline(4096).decode("ascii", "replace").strip()
        parts = line.split()
        destination = proxy_decision(parts[0], parts[1]) if len(parts) == 3 else None
        for _ in range(64):
            header = self.rfile.readline(4096)
            if header in (b"\r\n", b"\n", b""):
                break
        else:
            self.wfile.write(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
            return
        if destination is None:
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return
        try:
            upstream = socket.create_connection(destination, timeout=10)
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        with upstream:
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            sockets = [self.connection, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                if not readable:
                    return
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    with _Server((args.listen, args.port), _TunnelHandler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
