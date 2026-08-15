from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import Endpoint
from .providers.base import ProviderError


HERMES_BASELINE_SHA = "f80f453ae0679347e38abc917c7f94f717bf96c5"
HERMES_BASELINE_VERSION = "0.20.1"
HERMES_MANIFEST_SCHEMA = "wh-hermes-fixture/v1"
_PREFLIGHT_EXIT = 86
_POLICY_EXIT = 87
_MAX_FILE_BYTES = 256 * 1024
_MAX_TOTAL_BYTES = 512 * 1024
_MAX_RUNTIME_FILE_BYTES = 64 * 1024 * 1024
_MAX_PROMPT_CHARS = 16_000
_PROBE_NAME = "wallbreaker-lab-probe"
_RESERVED_ENV_KEYS = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "HERMES_ENABLE_PROJECT_PLUGINS",
        "HERMES_HOME",
        "HERMES_INFERENCE_MODEL",
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_PROFILE",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WALLBREAKER_HERMES_ATTESTATION",
        "WALLBREAKER_HERMES_PROBE_MODE",
        "WALLBREAKER_HERMES_SEAL",
        "WINDIR",
    }
)
_ALLOWED_FILES = {
    "SOUL.md": ("home", "SOUL.md"),
    "memories/MEMORY.md": ("home", "memories", "MEMORY.md"),
    "memories/USER.md": ("home", "memories", "USER.md"),
    "workspace/AGENTS.md": ("cwd", "AGENTS.md"),
}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|ghp|github_pat|AKIA)[-_A-Za-z0-9]{12,}\b"),
    re.compile(
        r"(?im)^\s*(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+"
    ),
)
_PROBE_SOURCE = '''import hashlib
import json
import os
from pathlib import Path


def _write_attestation(**kwargs):
    request = kwargs.get("request")
    body = request.get("body") if isinstance(request, dict) else None
    body_valid = isinstance(body, dict) and isinstance(body.get("messages"), list)
    request_tools = body.get("tools", []) if body_valid else None
    request_functions = body.get("functions", []) if body_valid else None
    messages = kwargs.get("request_messages")
    messages_valid = (
        isinstance(messages, list)
        and bool(messages)
        and all(isinstance(message, dict) for message in messages)
    )
    messages = messages if isinstance(messages, list) else []
    seal = os.environ.get("WALLBREAKER_HERMES_SEAL", "")
    roles = []
    sizes = []
    hashes = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        roles.append(str(message.get("role", "")))
        content = json.dumps(message.get("content"), ensure_ascii=False, sort_keys=True)
        sizes.append(len(content.encode("utf-8")))
        hashes.append(hashlib.sha256((seal + content).encode("utf-8")).hexdigest())
    try:
        from tools.mcp_tool import _load_mcp_config
        mcp_count = len(_load_mcp_config())
    except Exception:
        mcp_count = -1
    tool_count = int(kwargs.get("tool_count", -1))
    request_tool_count = (
        len(request_tools) + len(request_functions)
        if isinstance(request_tools, list) and isinstance(request_functions, list)
        else -1
    )
    payload = {
        "schema": "wallbreaker.hermes-lab.attestation/v1",
        "mode": os.environ.get("WALLBREAKER_HERMES_PROBE_MODE", ""),
        "provider": str(kwargs.get("provider", "")),
        "model": str(kwargs.get("model", "")),
        "profile": os.environ.get("HERMES_PROFILE", ""),
        "roles": roles,
        "message_sizes": sizes,
        "message_hashes": hashes,
        "tool_count": tool_count,
        "request_tool_count": request_tool_count,
        "request_valid": body_valid and messages_valid,
        "mcp_count": mcp_count,
        "endpoint_origin_hash": hashlib.sha256(
            (seal + str(kwargs.get("base_url", ""))).encode("utf-8")
        ).hexdigest(),
        "seal": seal,
    }
    path = Path(os.environ["WALLBREAKER_HERMES_ATTESTATION"])
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    valid = (
        body_valid
        and messages_valid
        and tool_count == 0
        and request_tool_count == 0
        and mcp_count == 0
    )
    if payload["mode"] == "preflight":
        os._exit(86 if valid else 87)
    if not valid:
        os._exit(87)


def _block_tool_call(**kwargs):
    return {"action": "block", "message": "Hermes laboratory targets cannot call tools."}


def register(ctx):
    ctx.register_hook("pre_api_request", _write_attestation)
    ctx.register_hook("pre_tool_call", _block_tool_call)
'''


class HermesLabTimeout(ProviderError):
    pass


@dataclass(frozen=True)
class CleanupReceipt:
    outcome: str
    root_removed: bool
    process_reaped: bool
    source_unchanged: bool


@dataclass(frozen=True)
class HermesLabResult:
    text: str
    input_tokens: int
    output_tokens: int
    replica_changed: bool
    cleanup: CleanupReceipt


class HermesLabReplica:
    def __init__(self, endpoint: Endpoint, timeout: float) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.runtime = Path(endpoint.hermes_runtime)
        self.python = Path(endpoint.hermes_python)
        self.manifest_path = Path(endpoint.hermes_manifest)
        self.context_root = Path(endpoint.hermes_context_root) if endpoint.hermes_context_root else None
        self.root: Path | None = None
        self.home: Path | None = None
        self.cwd: Path | None = None
        self.usage_path: Path | None = None
        self.preflight_path: Path | None = None
        self.run_attestation_path: Path | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._source_files: dict[str, Path] = {}
        self._runtime_files: dict[str, Path] = {}
        self._context_handle: int | tuple[int, ...] | None = None
        self._source_snapshot: dict[str, str] = {}
        self._runtime_snapshot: dict[str, str] = {}
        self._replica_snapshot: dict[str, str] = {}
        self._seal = ""
        self.cleanup_receipt: CleanupReceipt | None = None

    def prepare(self, max_tokens: int) -> None:
        self._validate_runtime()
        manifest = self._load_manifest()
        self.root = Path(tempfile.mkdtemp(prefix="wallbreaker-hermes-lab-"))
        self._secure_root()
        self.home = self.root / "home"
        self.cwd = self.root / "cwd"
        for path in (
            self.home,
            self.cwd,
            self.root / "tmp",
            self.root / "appdata",
            self.root / "localappdata",
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.usage_path = self.root / "usage.json"
        self.preflight_path = self.root / "preflight.json"
        self.run_attestation_path = self.root / "run-attestation.json"
        self._write_runtime_files(max_tokens)
        self._copy_manifest_files(manifest["files"])
        self._source_snapshot = self._snapshot_sources()
        self._runtime_snapshot = self._snapshot(
            self._runtime_files, limit=_MAX_RUNTIME_FILE_BYTES
        )
        self._replica_snapshot = self._snapshot(self._replica_files())
        if self._source_snapshot != self._replica_snapshot:
            raise ProviderError("Hermes laboratory context changed while it was copied.")
        self._seal = self._current_seal()

    async def execute(self, prompt: str, max_tokens: int) -> HermesLabResult:
        if len(prompt) > _MAX_PROMPT_CHARS:
            raise ProviderError(
                f"Hermes laboratory prompts are limited to {_MAX_PROMPT_CHARS} characters."
            )
        outcome = "error"
        try:
            self.prepare(max_tokens)
            preflight_code, _, _ = await self._run_process("preflight", prompt)
            if preflight_code != _PREFLIGHT_EXIT:
                raise ProviderError("Hermes laboratory preflight did not stop before inference.")
            self._validate_attestation(self.preflight_path, "preflight")
            if self._current_seal() != self._seal:
                raise ProviderError("Hermes laboratory inputs changed after preflight.")
            if self._snapshot(self._replica_files()) != self._replica_snapshot:
                raise ProviderError("Hermes laboratory replica changed during preflight.")
            code, stdout, _ = await self._run_process("run", prompt)
            if code == _POLICY_EXIT:
                raise ProviderError("Hermes laboratory request violated the zero-tools policy.")
            if code != 0:
                raise ProviderError(f"Hermes laboratory process exited with code {code}.")
            self._validate_attestation(self.run_attestation_path, "run")
            self._validate_runtime()
            if self._snapshot(
                self._runtime_files, limit=_MAX_RUNTIME_FILE_BYTES
            ) != self._runtime_snapshot:
                raise ProviderError("Hermes laboratory runtime changed during execution.")
            usage = self._read_usage()
            replica_changed = self._snapshot(self._replica_files()) != self._replica_snapshot
            if replica_changed:
                raise ProviderError("Hermes laboratory replica changed during execution.")
            text = stdout.decode("utf-8", "replace").rstrip("\r\n")
            if not text:
                raise ProviderError("Hermes laboratory process returned no final response.")
            outcome = "success"
            receipt = await self.close(outcome)
            return HermesLabResult(
                text=text,
                input_tokens=usage[0],
                output_tokens=usage[1],
                replica_changed=replica_changed,
                cleanup=receipt,
            )
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except HermesLabTimeout:
            outcome = "timeout"
            raise
        finally:
            if self.cleanup_receipt is None:
                await self.close(outcome)

    async def close(self, outcome: str = "error") -> CleanupReceipt:
        if self.cleanup_receipt is not None:
            return self.cleanup_receipt
        process_reaped = True
        if self._process is not None and self._process.returncode is None:
            process_reaped = await self._terminate_process(self._process)
        source_unchanged = self._snapshot_sources() == self._source_snapshot
        if self._context_handle is not None:
            _close_context_root(self._context_handle)
            self._context_handle = None
        root_removed = True
        if self.root is not None and self.root.exists():
            try:
                await asyncio.to_thread(shutil.rmtree, self.root)
            except OSError:
                root_removed = False
        root_removed = root_removed and (self.root is None or not self.root.exists())
        self.cleanup_receipt = CleanupReceipt(
            outcome=outcome,
            root_removed=root_removed,
            process_reaped=process_reaped,
            source_unchanged=source_unchanged,
        )
        if not (root_removed and process_reaped and source_unchanged):
            raise ProviderError("Hermes laboratory cleanup could not be verified.")
        return self.cleanup_receipt

    def _validate_runtime(self) -> None:
        try:
            runtime = self.runtime.resolve(strict=True)
            python = self.python.resolve(strict=True)
        except OSError as exc:
            raise ProviderError("Hermes runtime or Python is missing.") from exc
        if not runtime.is_dir() or not python.is_file() or not _is_within(python, runtime):
            raise ProviderError("Hermes runtime and Python must be absolute paths in one checkout.")
        if not self.runtime.is_absolute() or not self.python.is_absolute():
            raise ProviderError("Hermes runtime and Python paths must be absolute.")
        if _is_link_or_reparse(self.runtime) or _is_link_or_reparse(self.python):
            raise ProviderError("Hermes runtime paths cannot be links or reparse points.")
        allowed_dotenv = {".env.example", ".envrc"}
        if any(
            path.is_file() and path.name not in allowed_dotenv
            for path in runtime.glob(".env*")
        ) or (runtime / ".op.env").exists():
            raise ProviderError("Hermes package root contains a dotenv file.")
        if os.environ.get("HERMES_MANAGED_DIR", "").strip() or os.environ.get(
            "HERMES_MANAGED", ""
        ).strip():
            raise ProviderError("An inherited Hermes managed scope is active.")
        if os.name != "nt" and Path("/etc/hermes").is_dir():
            raise ProviderError("The default Hermes managed scope is active.")
        top = self._git("rev-parse", "--show-toplevel")
        head = self._git("rev-parse", "HEAD")
        dirty = self._git("status", "--porcelain", "--untracked-files=all")
        if Path(top).resolve() != runtime or head != HERMES_BASELINE_SHA or dirty:
            raise ProviderError("Hermes runtime is not the clean approved baseline checkout.")
        script = (
            "import importlib.metadata,importlib.util,json;"
            "names=('run_agent','hermes_cli.main','tools.mcp_tool');"
            "origins={n:(s.origin if (s:=importlib.util.find_spec(n)) else '') for n in names};"
            "print(json.dumps({'version':importlib.metadata.version('hermes-agent'),"
            "'origins':origins}))"
        )
        completed = subprocess.run(
            [str(python), "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=15,
            env=self._identity_env(),
            check=False,
        )
        try:
            identity = json.loads(completed.stdout)
            origins = {
                name: Path(origin).resolve(strict=True)
                for name, origin in identity["origins"].items()
            }
        except (AttributeError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("Hermes Python identity could not be verified.") from exc
        if (
            completed.returncode != 0
            or identity.get("version") != HERMES_BASELINE_VERSION
            or set(origins) != {"run_agent", "hermes_cli.main", "tools.mcp_tool"}
            or any(not _is_within(origin, runtime) for origin in origins.values())
            or any(_is_link_or_reparse(origin) for origin in origins.values())
        ):
            raise ProviderError("Hermes Python does not resolve to the approved baseline.")
        for origin in origins.values():
            self._git(
                "ls-files",
                "--error-unmatch",
                "--",
                origin.relative_to(runtime).as_posix(),
            )
        for path in (python, *origins.values()):
            _read_regular_bytes(path, _MAX_RUNTIME_FILE_BYTES)
        self.runtime = runtime
        self.python = python
        self._runtime_files = {"python": python, **origins}

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.runtime), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise ProviderError("Hermes runtime Git identity could not be verified.")
        return completed.stdout.strip()

    def _load_manifest(self) -> dict:
        raw = _read_regular_utf8(self.manifest_path, _MAX_FILE_BYTES)
        try:
            manifest = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("Hermes laboratory manifest is not valid JSON.") from exc
        expected_keys = {"schema", "mode", "provider", "model", "files", "expected_tool_count"}
        if not isinstance(manifest, dict) or set(manifest) != expected_keys:
            raise ProviderError("Hermes laboratory manifest has an unsupported shape.")
        if manifest["schema"] != HERMES_MANIFEST_SCHEMA:
            raise ProviderError("Hermes laboratory manifest schema is unsupported.")
        if manifest["mode"] not in {"clean", "selected"}:
            raise ProviderError("Hermes laboratory manifest mode must be clean or selected.")
        if manifest["provider"] != self.endpoint.hermes_provider or manifest["model"] != self.endpoint.model:
            raise ProviderError("Hermes laboratory manifest provider or model does not match the target.")
        if manifest["expected_tool_count"] != 0:
            raise ProviderError("Hermes laboratory manifests must require zero tools.")
        files = manifest["files"]
        if not isinstance(files, list) or any(not isinstance(item, str) for item in files):
            raise ProviderError("Hermes laboratory manifest files must be a list of paths.")
        if len(files) != len(set(item.casefold() for item in files)):
            raise ProviderError("Hermes laboratory manifest contains a path collision.")
        if any(item not in _ALLOWED_FILES for item in files):
            raise ProviderError("Hermes laboratory manifest contains a blocked path.")
        if manifest["mode"] == "clean" and files:
            raise ProviderError("Clean Hermes laboratory manifests cannot copy files.")
        if manifest["mode"] == "selected" and (not files or self.context_root is None):
            raise ProviderError("Selected Hermes laboratory manifests need files and a context root.")
        return manifest

    def _write_runtime_files(self, max_tokens: int) -> None:
        assert self.home is not None
        config = {
            "model": {
                "default": self.endpoint.model,
                "provider": self.endpoint.hermes_provider,
                "max_tokens": max_tokens,
                "context_length": 131072,
            },
            "context": {"engine": "compressor"},
            "plugins": {"enabled": [_PROBE_NAME], "disabled": []},
            "mcp_servers": {},
        }
        _write_private_text(self.home / "config.yaml", json.dumps(config, indent=2) + "\n")
        plugin = self.home / "plugins" / _PROBE_NAME
        plugin.mkdir(parents=True)
        _write_private_text(
            plugin / "plugin.yaml",
            json.dumps({"name": _PROBE_NAME, "version": "1.0.0"}) + "\n",
        )
        _write_private_text(plugin / "__init__.py", _PROBE_SOURCE)

    def _copy_manifest_files(self, logical_files: list[str]) -> None:
        if not logical_files:
            return
        assert self.context_root is not None and self.home is not None and self.cwd is not None
        root = self.context_root
        if not root.is_absolute() or (os.name == "nt" and str(root).startswith("\\\\")):
            raise ProviderError("Hermes context root must be an absolute regular directory.")
        self._context_handle = _open_context_root(root)
        total = 0
        for logical in logical_files:
            relative = PurePosixPath(logical)
            source = root.joinpath(*relative.parts)
            raw = _read_context_bytes(
                root, relative, _MAX_FILE_BYTES, self._context_handle
            )
            total += len(raw)
            if total > _MAX_TOTAL_BYTES:
                raise ProviderError("Hermes laboratory context exceeds the copy limit.")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProviderError(f"Hermes context file is not UTF-8: {logical}") from exc
            if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
                raise ProviderError(f"Hermes context file matches a blocked secret pattern: {logical}")
            target_parts = _ALLOWED_FILES[logical]
            base = self.home if target_parts[0] == "home" else self.cwd
            destination = base.joinpath(*target_parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_private_bytes(destination, raw)
            self._source_files[logical] = source

    def _replica_files(self) -> dict[str, Path]:
        if self.home is None or self.cwd is None:
            return {}
        files: dict[str, Path] = {}
        for logical in self._source_files:
            parts = _ALLOWED_FILES[logical]
            base = self.home if parts[0] == "home" else self.cwd
            files[logical] = base.joinpath(*parts[1:])
        return files

    def _snapshot_sources(self) -> dict[str, str]:
        if self.context_root is None:
            return {}
        if self._context_handle is None:
            return {logical: "missing" for logical in self._source_files}
        snapshot: dict[str, str] = {}
        for logical in sorted(self._source_files):
            try:
                raw = _read_context_bytes(
                    self.context_root,
                    PurePosixPath(logical),
                    _MAX_FILE_BYTES,
                    self._context_handle,
                )
            except (OSError, ProviderError):
                snapshot[logical] = "missing"
                continue
            snapshot[logical] = _content_digest(logical, raw)
        return snapshot

    def _snapshot(
        self, files: dict[str, Path], *, limit: int = _MAX_FILE_BYTES
    ) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for logical, path in sorted(files.items()):
            try:
                raw = _read_regular_bytes(path, limit)
            except (OSError, ProviderError):
                snapshot[logical] = "missing"
                continue
            snapshot[logical] = _content_digest(logical, raw)
        return snapshot

    def _current_seal(self) -> str:
        self._validate_runtime()
        digest = hashlib.sha256(HERMES_BASELINE_SHA.encode("ascii"))
        digest.update(_read_regular_bytes(self.manifest_path, _MAX_FILE_BYTES))
        for logical, value in sorted(
            self._snapshot(self._runtime_files, limit=_MAX_RUNTIME_FILE_BYTES).items()
        ):
            digest.update(logical.encode("utf-8"))
            digest.update(value.encode("ascii"))
        for logical, value in sorted(self._snapshot_sources().items()):
            digest.update(logical.encode("utf-8"))
            digest.update(value.encode("ascii"))
        if self.home is not None:
            for relative in (
                "config.yaml",
                f"plugins/{_PROBE_NAME}/plugin.yaml",
                f"plugins/{_PROBE_NAME}/__init__.py",
            ):
                digest.update(_read_regular_bytes(self.home / relative, _MAX_FILE_BYTES))
        return digest.hexdigest()

    def _secure_root(self) -> None:
        assert self.root is not None
        if os.name != "nt":
            self.root.chmod(0o700)
            if stat.S_IMODE(self.root.stat().st_mode) & 0o077:
                raise ProviderError("Hermes laboratory root permissions are not private.")
            return
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        try:
            sid = next(csv.reader([identity.stdout.strip()]))[1]
        except (IndexError, StopIteration) as exc:
            raise ProviderError("Current Windows identity could not be resolved.") from exc
        secured = subprocess.run(
            ["icacls", str(self.root), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "/Q"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if identity.returncode != 0 or secured.returncode != 0:
            raise ProviderError("Hermes laboratory root ACL could not be secured.")

    def _identity_env(self) -> dict[str, str]:
        env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        env["PATH"] = str(self.python.parent)
        if os.name == "nt" and env.get("SYSTEMROOT"):
            env["PATH"] += os.pathsep + str(Path(env["SYSTEMROOT"]) / "System32")
        else:
            env["PATH"] += os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        return env

    def _child_env(self, mode: str) -> dict[str, str]:
        assert self.root is not None and self.home is not None and self.cwd is not None
        attestation = self.preflight_path if mode == "preflight" else self.run_attestation_path
        env = self._identity_env()
        env.update(
            {
                "HERMES_HOME": str(self.home),
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "APPDATA": str(self.root / "appdata"),
                "LOCALAPPDATA": str(self.root / "localappdata"),
                "TEMP": str(self.root / "tmp"),
                "TMP": str(self.root / "tmp"),
                "HERMES_ENABLE_PROJECT_PLUGINS": "0",
                "HERMES_INFERENCE_MODEL": self.endpoint.model,
                "HERMES_INFERENCE_PROVIDER": self.endpoint.hermes_provider,
                "WALLBREAKER_HERMES_PROBE_MODE": mode,
                "WALLBREAKER_HERMES_ATTESTATION": str(attestation),
                "WALLBREAKER_HERMES_SEAL": self._seal,
            }
        )
        key_name = self.endpoint.api_key_env
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_name):
            raise ProviderError("Hermes laboratory api_key_env is invalid.")
        if key_name.upper() in _RESERVED_ENV_KEYS:
            raise ProviderError("Hermes laboratory api_key_env collides with a reserved variable.")
        key = self.endpoint.resolved_key()
        if not key:
            raise ProviderError(f"Hermes laboratory credential is missing from {key_name}.")
        env[key_name] = key
        return env

    async def _run_process(self, mode: str, prompt: str) -> tuple[int, bytes, bytes]:
        assert self.cwd is not None and self.usage_path is not None
        argv = [
            str(self.python),
            "-I",
            "-m",
            "hermes_cli.main",
            "--provider",
            self.endpoint.hermes_provider,
            "--model",
            self.endpoint.model,
            "--toolsets",
            "context_engine",
            "--usage-file",
            str(self.usage_path),
            "-z",
            prompt,
        ]
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.cwd),
            env=self._child_env(mode),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        process = self._process
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            return process.returncode or 0, stdout, stderr
        except (asyncio.TimeoutError, TimeoutError) as exc:
            await asyncio.shield(self._terminate_process(process))
            raise HermesLabTimeout(
                f"Hermes laboratory process timed out after {self.timeout:g} seconds."
            ) from exc
        except asyncio.CancelledError:
            await asyncio.shield(self._terminate_process(process))
            raise
        finally:
            if process.returncode is not None:
                self._process = None

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> bool:
        if process.returncode is not None:
            return True
        try:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError, asyncio.TimeoutError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except (OSError, asyncio.TimeoutError):
            return False
        finally:
            if process.returncode is not None:
                self._process = None
        return process.returncode is not None

    def _validate_attestation(self, path: Path | None, mode: str) -> dict:
        if path is None:
            raise ProviderError("Hermes laboratory attestation path is missing.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError("Hermes laboratory attestation is missing or invalid.") from exc
        roles = data.get("roles")
        sizes = data.get("message_sizes")
        hashes = data.get("message_hashes")
        request_shape_valid = (
            data.get("request_valid") is True
            and data.get("profile") == ""
            and isinstance(roles, list)
            and bool(roles)
            and all(isinstance(role, str) and role for role in roles)
            and "user" in roles
            and isinstance(sizes, list)
            and len(sizes) == len(roles)
            and all(isinstance(size, int) and size >= 0 for size in sizes)
            and isinstance(hashes, list)
            and len(hashes) == len(roles)
            and all(
                isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in hashes
            )
            and isinstance(data.get("endpoint_origin_hash"), str)
            and re.fullmatch(r"[0-9a-f]{64}", data["endpoint_origin_hash"])
        )
        if (
            data.get("schema") != "wallbreaker.hermes-lab.attestation/v1"
            or data.get("mode") != mode
            or data.get("provider") != self.endpoint.hermes_provider
            or data.get("model") != self.endpoint.model
            or data.get("seal") != self._seal
            or data.get("tool_count") != 0
            or data.get("request_tool_count") != 0
            or data.get("mcp_count") != 0
            or not request_shape_valid
        ):
            raise ProviderError("Hermes laboratory attestation failed.")
        return data

    def _read_usage(self) -> tuple[int, int]:
        if self.usage_path is None:
            return 0, 0
        try:
            data = json.loads(self.usage_path.read_text(encoding="utf-8"))
            return int(data.get("input_tokens") or 0), int(data.get("output_tokens") or 0)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return 0, 0


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & 0x400)


def _content_digest(logical: str, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(logical.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(len(content)).encode("ascii"))
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()


def _open_context_root(root: Path) -> int | tuple[int, ...]:
    if os.name == "nt":
        handles = []
        try:
            for directory in [*reversed(root.parents), root]:
                handles.append(_open_windows_path(directory, directory=True))
            return tuple(handles)
        except Exception:
            for handle in reversed(handles):
                _close_windows_handle(handle)
            raise
    try:
        descriptor = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
    except OSError as exc:
        raise ProviderError(
            "Hermes context root must be an absolute regular directory."
        ) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ProviderError("Hermes context root must be an absolute regular directory.")
    return descriptor


def _close_context_root(handle: int | tuple[int, ...]) -> None:
    if os.name == "nt":
        assert isinstance(handle, tuple)
        for item in reversed(handle):
            _close_windows_handle(item)
    else:
        assert isinstance(handle, int)
        os.close(handle)


def _read_context_bytes(
    root: Path,
    relative: PurePosixPath,
    limit: int,
    root_handle: int | tuple[int, ...],
) -> bytes:
    if os.name == "nt":
        assert isinstance(root_handle, tuple)
        handles = []
        try:
            current = root
            for part in relative.parts[:-1]:
                current /= part
                handles.append(_open_windows_path(current, directory=True))
            return _read_regular_bytes(current / relative.parts[-1], limit)
        finally:
            for handle in reversed(handles):
                _close_windows_handle(handle)

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptors = []
    file_descriptor = None
    try:
        assert isinstance(root_handle, int)
        descriptors.append(os.dup(root_handle))
        for part in relative.parts[:-1]:
            descriptors.append(os.open(part, directory_flags, dir_fd=descriptors[-1]))
        file_descriptor = os.open(
            relative.parts[-1], file_flags, dir_fd=descriptors[-1]
        )
        return _read_descriptor(file_descriptor, root / Path(*relative.parts), limit)
    except OSError as exc:
        raise ProviderError(f"Hermes context path cannot contain links: {relative}") from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_regular_bytes(path: Path, limit: int) -> bytes:
    descriptor = _open_no_follow(path)
    try:
        return _read_descriptor(descriptor, path, limit)
    finally:
        os.close(descriptor)


def _read_descriptor(descriptor: int, path: Path, limit: int) -> bytes:
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProviderError(
            f"Hermes laboratory input is not a standalone regular file: {path.name}"
        )
    if info.st_size > limit:
        raise ProviderError(f"Hermes laboratory input exceeds {limit} bytes: {path.name}")
    chunks = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    content = b"".join(chunks)
    if len(content) > limit:
        raise ProviderError(f"Hermes laboratory input exceeds {limit} bytes: {path.name}")
    return content


def _open_no_follow(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if os.name != "nt":
        try:
            return os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as exc:
            raise ProviderError(
                f"Hermes laboratory input is not a standalone regular file: {path.name}"
            ) from exc

    import msvcrt

    handle = _open_windows_path(path)
    try:
        return msvcrt.open_osfhandle(handle, flags)
    except Exception:
        _close_windows_handle(handle)
        raise


def _open_windows_path(path: Path, *, directory: bool = False) -> int:
    import ctypes
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = create_file(
        str(path),
        0x00000080 if directory else 0x80000000,
        0x00000001,
        None,
        3,
        flags,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ProviderError(f"Hermes laboratory input could not be opened: {path.name}")
    try:
        info = FileAttributeTagInfo()
        if not kernel32.GetFileInformationByHandleEx(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.file_attributes & 0x00000400 or (
            directory and not info.file_attributes & 0x00000010
        ):
            raise ProviderError(f"Hermes context path cannot contain links: {path.name}")
        return handle
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def _close_windows_handle(handle: int) -> None:
    import ctypes

    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def _read_regular_utf8(path: Path, limit: int) -> str:
    try:
        return _read_regular_bytes(path, limit).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderError(f"Hermes laboratory input is not UTF-8: {path.name}") from exc


def _write_private_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(content)
    path.chmod(0o600)


def _write_private_text(path: Path, content: str) -> None:
    _write_private_bytes(path, content.encode("utf-8"))
