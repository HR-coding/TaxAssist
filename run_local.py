"""
Local dev server that listens on BOTH IPv4 (127.0.0.1) and IPv6 (::1) so the browser
works whether it resolves `localhost` to ::1 or 127.0.0.1. (Cloud Run uses the
Dockerfile's 0.0.0.0 bind instead — this file is local-only.)

Run:  python run_local.py
"""
import asyncio
import os
import socket
import uvicorn
from app.main import app

PORT = int(os.getenv("PORT", "8080"))


def _dual_stack_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # Accept IPv4 connections on the same IPv6 socket (dual stack).
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", PORT))
    sock.listen(128)
    sock.set_inheritable(True)
    return sock


def main():
    sock = _dual_stack_socket()
    config = uvicorn.Config(app, proxy_headers=True, forwarded_allow_ips="*",
                            log_level="info")
    server = uvicorn.Server(config)
    print(f"Serving on http://localhost:{PORT} and http://127.0.0.1:{PORT} (dual-stack)")
    asyncio.run(server.serve(sockets=[sock]))


if __name__ == "__main__":
    main()
