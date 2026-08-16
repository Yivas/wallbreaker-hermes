"""Dashboard authentication + CSRF/Origin enforcement.

The dashboard used to be a fully unauthenticated local API whose routes could spawn shell
commands, write API keys to .env, and fire attacks — reachable via browser CSRF from any page
the operator visited, and via the LAN if bound to 0.0.0.0 (audit SEC-1/2/3/6). This module adds:

  * a per-launch bearer token (generated on `serve()`, printed to the console, written 0600
    on POSIX and with a protected current-user/System/Administrators DACL on Windows);
  * a pure-ASGI SecurityMiddleware that requires the token AND a same-origin request on every
    /api/* route (except a small exempt set), rejecting cross-site requests before any handler
    side effect. Pure-ASGI (not BaseHTTPMiddleware) so it never buffers the SSE streams.

CORS is NOT an access control — Starlette's CORSMiddleware only decides response headers and lets
the handler run regardless. This middleware actually rejects the request.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

# The token IS the CSRF defense, not a separate header: it rides in a custom header a
# cross-site page cannot set (a cross-site fetch with a custom header triggers a CORS preflight,
# which this app's loopback-only CORS rejects), and cannot read (same-origin policy blocks
# /api/session). The Origin / Sec-Fetch-Site same-origin check is an independent, explicit
# CSRF guard. There is no cookie auth, so a double-submit CSRF token would add nothing.
TOKEN_HEADER = "x-wb-token"
TOKEN_FILENAME = ".wallbreaker_dashboard_token"

# Paths reachable without a token (health probe + the same-origin bootstrap the SPA uses to
# learn the token). Everything else under /api/ requires auth when require_auth is True.
EXEMPT_PATHS = frozenset({"/api/health", "/api/session"})

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


def token_file_path(base: str | Path | None = None) -> Path:
    return Path(base or ".") / TOKEN_FILENAME


def _windows_current_sid() -> str:
    import csv
    import re
    import subprocess

    whoami = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
    result = subprocess.run(
        [str(whoami), "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    row = next(csv.reader([result.stdout.strip()]), [])
    sid = row[1].strip() if len(row) > 1 else ""
    if not re.fullmatch(r"S-\d-\d+(?:-\d+)+", sid):
        raise OSError("could not resolve the current Windows user SID")
    return sid


def _windows_private_fd(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor = wintypes.LPVOID()
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), wintypes.LPVOID]
    convert.restype = wintypes.BOOL
    sddl = f"D:P(A;;FA;;;{_windows_current_sid()})(A;;FA;;;SY)(A;;FA;;;BA)"
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())

    attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(SecurityAttributes),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    try:
        handle = create_file(str(path), 0x40040000, 0, ctypes.byref(attributes), 2, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            set_security = advapi32.SetKernelObjectSecurity
            set_security.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID]
            set_security.restype = wintypes.BOOL
            if not set_security(handle, 0x80000004, descriptor):
                raise ctypes.WinError(ctypes.get_last_error())
            return msvcrt.open_osfhandle(handle, os.O_WRONLY)
        except Exception:
            kernel32.CloseHandle(handle)
            raise
    finally:
        kernel32.LocalFree(descriptor)


def ensure_launch_token(base: str | Path | None = None) -> str:
    """Generate the launch token and persist it for the same-user SPA."""
    token = secrets.token_urlsafe(32)
    path = token_file_path(base)
    if os.name == "nt":
        fd = _windows_private_fd(path)
    else:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token)
    if os.name != "nt":
        os.chmod(path, 0o600)
    return token


def _bearer(auth_header: str | None) -> str | None:
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def origin_is_same_site(origin: str | None) -> bool:
    """A localhost dashboard's only legitimate Origin is a loopback host. Absent Origin means a
    non-browser client (curl / the CLI / a test) which cannot be a CSRF victim → allowed."""
    if origin is None:
        return True
    host = urlsplit(origin).hostname or ""
    return host.lower() in _LOOPBACK_HOSTS


class SecurityMiddleware:
    """Pure-ASGI token + Origin gate. Streaming responses pass through untouched."""

    def __init__(self, app, token: str, require_auth: bool = True,
                 exempt_paths: frozenset[str] = EXEMPT_PATHS):
        self.app = app
        self.token = token
        self.require_auth = require_auth
        self.exempt_paths = exempt_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.require_auth:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/api/") or path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}

        # CSRF: reject any cross-site Origin (and Sec-Fetch-Site: cross-site) before the handler.
        if not origin_is_same_site(headers.get("origin")):
            await self._reject(send, 403, "cross-site request blocked")
            return
        if headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
            await self._reject(send, 403, "cross-site request blocked")
            return

        supplied = headers.get(TOKEN_HEADER) or _bearer(headers.get("authorization"))
        if not supplied or not hmac.compare_digest(supplied, self.token):
            await self._reject(send, 401, "missing or invalid dashboard token")
            return

        await self.app(scope, receive, send)

    async def _reject(self, send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
