import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

from wallbreaker.agent.messages import Message, ToolUseBlock, user
from wallbreaker.config import Config, ConfigError, Endpoint, _endpoint_from_table
from wallbreaker.hermes_lab import (
    CleanupReceipt,
    HERMES_BASELINE_SHA,
    HERMES_MANIFEST_SCHEMA,
    HermesLabReplica,
    HermesLabResult,
    HermesLabTimeout,
    _PROBE_SOURCE,
)
from wallbreaker.providers.base import ProviderError
from wallbreaker.providers.factory import build_provider
from wallbreaker.providers.hermes_lab_provider import HermesLabProvider
from wallbreaker.tools.registry import ToolContext
from wallbreaker.tools.control import _finish
from wallbreaker.tools.target import _continue_target, _query_target


def _manifest(path: Path, *, mode="clean", files=None, provider="fixture-provider", model="fixture/model"):
    path.write_text(
        json.dumps(
            {
                "schema": HERMES_MANIFEST_SCHEMA,
                "mode": mode,
                "provider": provider,
                "model": model,
                "files": files or [],
                "expected_tool_count": 0,
            }
        ),
        encoding="utf-8",
    )
    return path


def _endpoint(tmp_path: Path, manifest: Path, context_root: Path | None = None) -> Endpoint:
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    python = runtime / ("python.exe" if os.name == "nt" else "python")
    python.touch(exist_ok=True)
    return Endpoint(
        name="target",
        protocol="hermes-lab",
        base_url="",
        model="fixture/model",
        api_key_env="FIXTURE_PROVIDER_KEY",
        timeout=5,
        system_mode="drop",
        cache=False,
        hermes_runtime=str(runtime.resolve()),
        hermes_python=str(python.resolve()),
        hermes_provider="fixture-provider",
        hermes_manifest=str(manifest.resolve()),
        hermes_context_root=str(context_root.resolve()) if context_root else "",
    )


def _replica(tmp_path: Path, monkeypatch, *, mode="clean", files=None, context_root=None):
    manifest = _manifest(tmp_path / "manifest.json", mode=mode, files=files)
    replica = HermesLabReplica(_endpoint(tmp_path, manifest, context_root), timeout=5)
    monkeypatch.setattr(replica, "_validate_runtime", lambda: None)
    monkeypatch.setattr(replica, "_secure_root", lambda: None)
    monkeypatch.setenv("FIXTURE_PROVIDER_KEY", "fixture-key")
    return replica


def _write_attestation(replica: HermesLabReplica, mode: str) -> None:
    path = replica.preflight_path if mode == "preflight" else replica.run_attestation_path
    assert path is not None
    path.write_text(
        json.dumps(
            {
                "schema": "wallbreaker.hermes-lab.attestation/v1",
                "mode": mode,
                "provider": replica.endpoint.hermes_provider,
                "model": replica.endpoint.model,
                "profile": "",
                "roles": ["system", "user"],
                "message_sizes": [6, 7],
                "message_hashes": ["0" * 64, "1" * 64],
                "tool_count": 0,
                "request_tool_count": 0,
                "request_valid": True,
                "mcp_count": 0,
                "endpoint_origin_hash": "0" * 64,
                "seal": replica._seal,
            }
        ),
        encoding="utf-8",
    )


def test_config_accepts_hermes_target_and_rejects_profile(tmp_path):
    table = {
        "protocol": "hermes-lab",
        "model": "fixture/model",
        "api_key_env": "FIXTURE_PROVIDER_KEY",
        "hermes_runtime": str((tmp_path / "runtime").resolve()),
        "hermes_python": str((tmp_path / "runtime" / "python.exe").resolve()),
        "hermes_provider": "fixture-provider",
        "hermes_manifest": str((tmp_path / "manifest.json").resolve()),
    }
    endpoint = _endpoint_from_table(
        "target", table, require_model=True, allow_hermes_lab=True
    )
    assert endpoint.protocol == "hermes-lab"
    assert endpoint.system_mode == "drop"
    assert endpoint.cache is False
    with pytest.raises(ConfigError, match=r"only for \[target\]"):
        _endpoint_from_table("profile", table)


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_url", "https://example.test"),
        ("api_key", "inline-secret"),
        ("system_prompt", "override"),
        ("reasoning", True),
        ("cache", True),
    ],
)
def test_config_rejects_hermes_unsafe_options(tmp_path, field, value):
    table = {
        "protocol": "hermes-lab",
        "model": "fixture/model",
        "api_key_env": "FIXTURE_PROVIDER_KEY",
        "hermes_runtime": str((tmp_path / "runtime").resolve()),
        "hermes_python": str((tmp_path / "runtime" / "python.exe").resolve()),
        "hermes_provider": "fixture-provider",
        "hermes_manifest": str((tmp_path / "manifest.json").resolve()),
        field: value,
    }
    with pytest.raises(ConfigError):
        _endpoint_from_table(
            "target", table, require_model=True, allow_hermes_lab=True
        )


def test_factory_builds_hermes_provider(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    assert isinstance(build_provider(_endpoint(tmp_path, manifest)), HermesLabProvider)


def test_selected_manifest_copies_only_approved_files(tmp_path, monkeypatch):
    source = tmp_path / "context"
    (source / "memories").mkdir(parents=True)
    (source / "workspace").mkdir()
    (source / "SOUL.md").write_text("Synthetic identity", encoding="utf-8")
    (source / "memories" / "MEMORY.md").write_text("Synthetic memory", encoding="utf-8")
    (source / "workspace" / "AGENTS.md").write_text("Synthetic rule", encoding="utf-8")
    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=["SOUL.md", "memories/MEMORY.md", "workspace/AGENTS.md"],
        context_root=source,
    )
    replica.prepare(1024)
    root = replica.root
    assert replica.home is not None and replica.cwd is not None and root is not None
    assert (replica.home / "SOUL.md").read_text(encoding="utf-8") == "Synthetic identity"
    assert (replica.home / "memories" / "MEMORY.md").read_text(encoding="utf-8") == "Synthetic memory"
    assert (replica.cwd / "AGENTS.md").read_text(encoding="utf-8") == "Synthetic rule"
    assert not (replica.home / ".env").exists()
    asyncio.run(replica.close("success"))
    assert not root.exists()


def test_manifest_rejects_unknown_path(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch, mode="selected", files=["secrets.txt"], context_root=tmp_path)
    with pytest.raises(ProviderError, match="blocked path"):
        replica.prepare(1024)


def test_context_rejects_secret_pattern(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    (source / "SOUL.md").write_text("api_key = fixture-secret-value", encoding="utf-8")
    replica = _replica(
        tmp_path, monkeypatch, mode="selected", files=["SOUL.md"], context_root=source
    )
    with pytest.raises(ProviderError, match="secret pattern"):
        replica.prepare(1024)
    asyncio.run(replica.close())


def test_context_rejects_hard_link(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    original = source / "original.md"
    original.write_text("Synthetic identity", encoding="utf-8")
    os.link(original, source / "SOUL.md")
    replica = _replica(
        tmp_path, monkeypatch, mode="selected", files=["SOUL.md"], context_root=source
    )
    with pytest.raises(ProviderError, match="standalone regular file"):
        replica.prepare(1024)
    asyncio.run(replica.close())


def test_context_rejects_symbolic_link(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    target = source / "target.md"
    target.write_text("Synthetic identity", encoding="utf-8")
    try:
        (source / "SOUL.md").symlink_to(target)
    except OSError:
        pytest.skip("Symbolic links are unavailable for this account")
    replica = _replica(
        tmp_path, monkeypatch, mode="selected", files=["SOUL.md"], context_root=source
    )
    with pytest.raises(ProviderError, match="links"):
        replica.prepare(1024)
    asyncio.run(replica.close())


def test_context_rejects_symbolic_link_directory(tmp_path, monkeypatch):
    source = tmp_path / "context"
    external = tmp_path / "external"
    source.mkdir()
    external.mkdir()
    (external / "MEMORY.md").write_text("Synthetic memory", encoding="utf-8")
    try:
        (source / "memories").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symbolic links are unavailable for this account")
    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=["memories/MEMORY.md"],
        context_root=source,
    )
    with pytest.raises(ProviderError, match="links"):
        replica.prepare(1024)
    asyncio.run(replica.close())


def test_context_root_replacement_fails_closed(tmp_path, monkeypatch):
    import wallbreaker.hermes_lab as hermes_lab

    source = tmp_path / "context"
    external = tmp_path / "external"
    source.mkdir()
    external.mkdir()
    (source / "SOUL.md").write_text("Approved identity", encoding="utf-8")
    (external / "SOUL.md").write_text("External identity", encoding="utf-8")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(external, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("Directory symbolic links are unavailable for this account")

    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=["SOUL.md"],
        context_root=source,
    )
    original_open = hermes_lab._open_context_root

    def replace_then_open(root):
        source.rename(tmp_path / "original-context")
        source.symlink_to(external, target_is_directory=True)
        return original_open(root)

    monkeypatch.setattr(hermes_lab, "_open_context_root", replace_then_open)
    with pytest.raises(ProviderError, match=r"context (?:root|path)"):
        replica.prepare(1024)
    asyncio.run(replica.close())


@pytest.mark.skipif(os.name != "nt", reason="Windows handle-sharing contract")
def test_context_ancestor_is_locked_until_cleanup(tmp_path, monkeypatch):
    container = tmp_path / "container"
    source = container / "context"
    source.mkdir(parents=True)
    (source / "SOUL.md").write_text("Approved identity", encoding="utf-8")
    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=["SOUL.md"],
        context_root=source,
    )
    replica.prepare(1024)
    moved = tmp_path / "moved-container"
    with pytest.raises(OSError):
        container.rename(moved)
    asyncio.run(replica.close())
    container.rename(moved)
    assert moved.is_dir()


@pytest.mark.parametrize("name", [".env", ".env.local", ".op.env"])
def test_runtime_rejects_package_dotenv_before_git(tmp_path, name):
    manifest = _manifest(tmp_path / "manifest.json")
    endpoint = _endpoint(tmp_path, manifest)
    (Path(endpoint.hermes_runtime) / name).write_text("FIXTURE=value", encoding="utf-8")
    replica = HermesLabReplica(endpoint, 5)
    with pytest.raises(ProviderError, match="dotenv"):
        replica._validate_runtime()


def test_runtime_rejects_missing_checkout(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    endpoint = Endpoint(
        name="target",
        protocol="hermes-lab",
        base_url="",
        model="fixture/model",
        api_key_env="FIXTURE_PROVIDER_KEY",
        hermes_runtime=str((tmp_path / "missing").resolve()),
        hermes_python=str((tmp_path / "missing" / "python.exe").resolve()),
        hermes_provider="fixture-provider",
        hermes_manifest=str(manifest.resolve()),
    )
    with pytest.raises(ProviderError, match="missing"):
        HermesLabReplica(endpoint, 5)._validate_runtime()


def test_runtime_rejects_managed_scope(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / "manifest.json")
    replica = HermesLabReplica(_endpoint(tmp_path, manifest), 5)
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(tmp_path / "managed"))
    with pytest.raises(ProviderError, match="managed scope"):
        replica._validate_runtime()


def test_runtime_rejects_wrong_sha(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / "manifest.json")
    replica = HermesLabReplica(_endpoint(tmp_path, manifest), 5)

    def fake_git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(replica.runtime)
        if args == ("rev-parse", "HEAD"):
            return "0" * 40
        return ""

    monkeypatch.setattr(replica, "_git", fake_git)
    with pytest.raises(ProviderError, match="approved baseline"):
        replica._validate_runtime()


def test_runtime_requires_tracked_startup_modules(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / "manifest.json")
    replica = HermesLabReplica(_endpoint(tmp_path, manifest), 5)
    runtime = replica.runtime
    (runtime / ".env.example").write_text("FIXTURE_KEY=\n", encoding="utf-8")
    (runtime / ".envrc").write_text("use flake\n", encoding="utf-8")
    origins = {}
    for name, relative in {
        "run_agent": "run_agent.py",
        "hermes_cli.main": "hermes_cli/main.py",
        "tools.mcp_tool": "tools/mcp_tool.py",
    }.items():
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
        origins[name] = str(path)

    tracked = []

    def fake_git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(runtime)
        if args == ("rev-parse", "HEAD"):
            return HERMES_BASELINE_SHA
        if args == ("status", "--porcelain", "--untracked-files=all"):
            return ""
        if args[:3] == ("ls-files", "--error-unmatch", "--"):
            tracked.append(args[3])
            return args[3]
        raise AssertionError(args)

    monkeypatch.setattr(replica, "_git", fake_git)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"version": "0.20.1", "origins": origins}),
        ),
    )
    replica._validate_runtime()
    assert set(replica._runtime_files) == {
        "python",
        "run_agent",
        "hermes_cli.main",
        "tools.mcp_tool",
    }
    assert sorted(tracked) == sorted(
        ["run_agent.py", "hermes_cli/main.py", "tools/mcp_tool.py"]
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"version": "0.20.0", "origins": origins}),
        ),
    )
    with pytest.raises(ProviderError, match="approved baseline"):
        replica._validate_runtime()


@pytest.mark.parametrize("name", [".env.example", ".envrc"])
def test_runtime_rejects_untracked_baseline_dotenv(tmp_path, monkeypatch, name):
    manifest = _manifest(tmp_path / "manifest.json")
    replica = HermesLabReplica(_endpoint(tmp_path, manifest), 5)
    (replica.runtime / name).write_text("FIXTURE_KEY=\n", encoding="utf-8")

    def fake_git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(replica.runtime)
        if args == ("rev-parse", "HEAD"):
            return HERMES_BASELINE_SHA
        if args == ("status", "--porcelain", "--untracked-files=all"):
            return f"?? {name}"
        raise AssertionError(args)

    monkeypatch.setattr(replica, "_git", fake_git)
    with pytest.raises(ProviderError, match="approved baseline"):
        replica._validate_runtime()


def test_child_environment_is_allowlisted(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    monkeypatch.setenv("SHOULD_NOT_REACH_HERMES", "canary")
    replica.prepare(1024)
    env = replica._child_env("preflight")
    assert env["FIXTURE_PROVIDER_KEY"] == "fixture-key"
    assert "SHOULD_NOT_REACH_HERMES" not in env
    assert "HERMES_MANAGED_DIR" not in env
    asyncio.run(replica.close())


def test_child_environment_rejects_reserved_credential_name(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.endpoint.api_key_env = "HERMES_PROFILE"
    monkeypatch.setenv("HERMES_PROFILE", "fixture-key")
    replica.prepare(1024)
    with pytest.raises(ProviderError, match="reserved variable"):
        replica._child_env("preflight")
    asyncio.run(replica.close())


def test_replica_seals_are_unlinkable(tmp_path, monkeypatch):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _replica(first_root, monkeypatch)
    second = _replica(second_root, monkeypatch)
    first.prepare(1024)
    second.prepare(1024)
    assert first._seal != second._seal
    asyncio.run(first.close())
    asyncio.run(second.close())


def test_probe_source_compiles():
    compile(_PROBE_SOURCE, "wallbreaker-lab-probe", "exec")


def test_probe_rejects_missing_request_body(tmp_path, monkeypatch):
    namespace = {}
    exec(_PROBE_SOURCE, namespace)

    class ProbeExit(Exception):
        pass

    tools = ModuleType("tools")
    tools.__path__ = []
    mcp_tool = ModuleType("tools.mcp_tool")
    setattr(mcp_tool, "_load_mcp_config", lambda: {})
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, "tools.mcp_tool", mcp_tool)
    path = tmp_path / "attestation.json"
    namespace["os"] = SimpleNamespace(
        environ={
            "WALLBREAKER_HERMES_ATTESTATION": str(path),
            "WALLBREAKER_HERMES_PROBE_MODE": "preflight",
            "WALLBREAKER_HERMES_SEAL": "fixture",
            "HERMES_PROFILE": "",
        },
        fsync=lambda _descriptor: None,
        replace=os.replace,
        _exit=lambda code: (_ for _ in ()).throw(ProbeExit(code)),
    )
    with pytest.raises(ProbeExit) as exc:
        namespace["_write_attestation"](
            request={"body": {}}, tool_count=0, request_messages=[]
        )
    assert exc.value.args == (87,)
    assert json.loads(path.read_text(encoding="utf-8"))["request_tool_count"] == 0

    messages = [
        {"role": "system", "content": "Synthetic system"},
        {"role": "user", "content": "Synthetic prompt"},
    ]
    with pytest.raises(ProbeExit) as exc:
        namespace["_write_attestation"](
            request={
                "body": {
                    "messages": messages,
                    "tools": [],
                    "functions": [{"name": "blocked"}],
                }
            },
            tool_count=0,
            request_messages=messages,
        )
    assert exc.value.args == (87,)
    assert json.loads(path.read_text(encoding="utf-8"))["request_tool_count"] == 1


def test_attestation_rejects_invalid_message_shape(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.prepare(1024)
    _write_attestation(replica, "preflight")
    assert replica.preflight_path is not None
    data = json.loads(replica.preflight_path.read_text(encoding="utf-8"))
    data["roles"] = []
    data["message_sizes"] = []
    data["message_hashes"] = []
    replica.preflight_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProviderError, match="attestation"):
        replica._validate_attestation(replica.preflight_path, "preflight")
    asyncio.run(replica.close())


@pytest.mark.parametrize(
    "roles",
    [
        ["user"],
        ["system", "developer", "user"],
        ["system", "user", "assistant"],
        ["system", "user", "tool"],
        ["system", "user", "user"],
    ],
)
def test_attestation_rejects_roles_outside_fixed_request(roles, tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.prepare(1024)
    _write_attestation(replica, "preflight")
    assert replica.preflight_path is not None
    data = json.loads(replica.preflight_path.read_text(encoding="utf-8"))
    data["roles"] = roles
    data["message_sizes"] = [1] * len(roles)
    data["message_hashes"] = ["0" * 64] * len(roles)
    replica.preflight_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProviderError, match="attestation"):
        replica._validate_attestation(replica.preflight_path, "preflight")
    asyncio.run(replica.close())


def test_temporary_root_permissions_can_be_secured(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    replica = HermesLabReplica(_endpoint(tmp_path, manifest), 5)
    root = tmp_path / "private-root"
    root.mkdir()
    replica.root = root
    replica._secure_root()
    assert root.is_dir()


def test_execute_preflights_runs_and_cleans(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    roots = []

    async def fake_run(mode, prompt):
        roots.append(replica.root)
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        assert replica.usage_path is not None
        replica.usage_path.write_text(
            json.dumps({"input_tokens": 12, "output_tokens": 5}), encoding="utf-8"
        )
        return 0, b"Synthetic response\n", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    result = asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert result.text == "Synthetic response"
    assert (result.input_tokens, result.output_tokens) == (12, 5)
    assert result.cleanup.root_removed is True
    assert not roots[-1].exists()


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_execute_rejects_known_credential_in_child_output(stream, tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        assert replica.usage_path is not None
        replica.usage_path.write_text("{}", encoding="utf-8")
        stdout = b"fixture-key" if stream == "stdout" else b"Synthetic response"
        stderr = b"fixture-key" if stream == "stderr" else b""
        return 0, stdout, stderr

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="secret") as error:
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert "fixture-key" not in str(error.value)


def test_execute_rejects_known_credential_in_allowed_state(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    (source / "SOUL.md").write_text("Synthetic identity", encoding="utf-8")
    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=["SOUL.md"],
        context_root=source,
    )

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        assert replica.home is not None and replica.usage_path is not None
        (replica.home / "SOUL.md").write_text("fixture-key", encoding="utf-8")
        replica.usage_path.write_text("{}", encoding="utf-8")
        return 0, b"Synthetic response", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="secret"):
        asyncio.run(
            replica.execute(
                "Synthetic prompt",
                1024,
                allowed_state_paths=frozenset({"SOUL.md"}),
            )
        )


def test_tool_or_mcp_attestation_aborts_and_cleans(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    root = None

    async def fake_run(mode, prompt):
        nonlocal root
        root = replica.root
        _write_attestation(replica, mode)
        assert replica.preflight_path is not None
        data = json.loads(replica.preflight_path.read_text(encoding="utf-8"))
        data["tool_count"] = 1
        replica.preflight_path.write_text(json.dumps(data), encoding="utf-8")
        return 86, b"", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="attestation"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert root is not None and not root.exists()


def test_timeout_cleans_replica(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    root = None

    async def fake_run(mode, prompt):
        nonlocal root
        root = replica.root
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        raise HermesLabTimeout("timeout")

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(HermesLabTimeout):
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert replica.cleanup_receipt is not None
    assert replica.cleanup_receipt.outcome == "timeout"
    assert root is not None and not root.exists()


@pytest.mark.asyncio
async def test_cancellation_cleans_replica(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    entered = asyncio.Event()

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(replica, "_run_process", fake_run)
    task = asyncio.create_task(replica.execute("Synthetic prompt", 1024))
    await entered.wait()
    root = replica.root
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert replica.cleanup_receipt is not None
    assert replica.cleanup_receipt.outcome == "cancelled"
    assert root is not None and not root.exists()


@pytest.mark.asyncio
async def test_cancellation_preserves_cancelled_error_when_cleanup_fails(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    entered = asyncio.Event()

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        entered.set()
        await asyncio.Event().wait()

    async def failed_close(outcome="error"):
        replica.cleanup_receipt = CleanupReceipt(outcome, False, True, True)
        raise ProviderError("Hermes laboratory cleanup could not be verified.")

    monkeypatch.setattr(replica, "_run_process", fake_run)
    monkeypatch.setattr(replica, "close", failed_close)
    task = asyncio.create_task(replica.execute("Synthetic prompt", 1024))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert replica.cleanup_receipt == CleanupReceipt("cancelled", False, True, True)


def test_source_change_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    source_file = source / "SOUL.md"
    source_file.write_text("Synthetic identity", encoding="utf-8")
    replica = _replica(
        tmp_path, monkeypatch, mode="selected", files=["SOUL.md"], context_root=source
    )

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        source_file.write_text("Changed identity", encoding="utf-8")
        return 86, b"", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="cleanup"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert replica.cleanup_receipt is not None
    assert replica.cleanup_receipt.source_unchanged is False


def test_replica_change_during_preflight_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "context"
    source.mkdir()
    (source / "SOUL.md").write_text("Synthetic identity", encoding="utf-8")
    replica = _replica(
        tmp_path, monkeypatch, mode="selected", files=["SOUL.md"], context_root=source
    )

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        assert replica.home is not None
        (replica.home / "SOUL.md").write_text("Changed identity", encoding="utf-8")
        return 86, b"", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="replica changed during preflight"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))


@pytest.mark.parametrize("name", [".env.example", ".envrc"])
def test_runtime_dotenv_change_during_execution_fails_closed(tmp_path, monkeypatch, name):
    replica = _replica(tmp_path, monkeypatch)
    dotenv = replica.runtime / name
    dotenv.write_text("tracked\n", encoding="utf-8")

    def validate_runtime():
        if dotenv.read_text(encoding="utf-8") != "tracked\n":
            raise ProviderError("Hermes runtime is not the clean approved baseline checkout.")

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        dotenv.write_text("changed\n", encoding="utf-8")
        return 0, b"Synthetic response", b""

    monkeypatch.setattr(replica, "_validate_runtime", validate_runtime)
    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="approved baseline"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))


def test_partial_cleanup_fails_closed(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    original_rmtree = shutil.rmtree

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        return 0, b"Synthetic response", b""

    def fail_rmtree(path):
        raise OSError("locked")

    monkeypatch.setattr(replica, "_run_process", fake_run)
    monkeypatch.setattr("wallbreaker.hermes_lab.shutil.rmtree", fail_rmtree)
    with pytest.raises(ProviderError, match="cleanup"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert replica.cleanup_receipt is not None
    assert replica.cleanup_receipt.root_removed is False
    assert replica.root is not None
    original_rmtree(replica.root)


@pytest.mark.asyncio
async def test_process_argv_uses_checked_runtime_and_zero_toolset(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.prepare(1024)
    captured = {}

    class FakeProcess:
        returncode = 86
        pid = 123

        async def communicate(self):
            return b"", b""

    async def fake_create(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    code, _, _ = await replica._run_process("preflight", "Synthetic prompt")
    argv = captured["args"]
    assert code == 86
    assert argv[:4] == (str(replica.python), "-I", "-m", "hermes_cli.main")
    assert argv[argv.index("--toolsets") + 1] == "context_engine"
    assert argv[-2:] == ("-z", "Synthetic prompt")
    assert "shell" not in captured["kwargs"]
    await replica.close()


@pytest.mark.asyncio
async def test_process_timeout_terminates_child(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.timeout = 0.001
    replica.prepare(1024)
    terminated = []

    class FakeProcess:
        returncode = None
        pid = 123

        async def communicate(self):
            await asyncio.sleep(1)

    process = FakeProcess()

    async def fake_create(*args, **kwargs):
        return process

    async def fake_terminate(value):
        terminated.append(value)
        value.returncode = -1
        return True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(replica, "_terminate_process", fake_terminate)
    with pytest.raises(HermesLabTimeout):
        await replica._run_process("run", "Synthetic prompt")
    assert terminated == [process]
    await replica.close("timeout")


@pytest.mark.asyncio
async def test_provider_rejects_unsupported_shapes_before_replica(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    provider = HermesLabProvider(_endpoint(tmp_path, manifest))
    with pytest.raises(ProviderError, match="one user turn"):
        await provider.complete([user("one"), user("two")])
    with pytest.raises(ProviderError, match="system prompt"):
        await provider.complete([user("one")], system="override")
    with pytest.raises(ProviderError, match="plain text"):
        await provider.complete(
            [Message(role="user", content=[ToolUseBlock("1", "tool", {})])]
        )
    with pytest.raises(ProviderError, match="temperature"):
        await provider.complete([user("one")], temperature=0.2)


@pytest.mark.asyncio
async def test_provider_creates_a_fresh_replica_per_call(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path / "manifest.json")
    provider = HermesLabProvider(_endpoint(tmp_path, manifest))
    created = []

    class FakeReplica:
        def __init__(self, endpoint, timeout):
            created.append(self)
            self.cleanup_receipt = None

        async def execute(self, prompt, max_tokens, **kwargs):
            self.cleanup_receipt = CleanupReceipt("success", True, True, True)
            return HermesLabResult("response", 1, 2, False, self.cleanup_receipt)

        async def close(self, outcome):
            return self.cleanup_receipt

    monkeypatch.setattr(
        "wallbreaker.providers.hermes_lab_provider.HermesLabReplica", FakeReplica
    )
    assert await provider.complete([user("one")]) == "response"
    assert await provider.complete([user("two")]) == "response"
    assert len(created) == 2


@pytest.mark.parametrize(
    "logical,component",
    [
        ("SOUL.md", "soul"),
        ("memories/MEMORY.md", "memory"),
        ("memories/USER.md", "user_memory"),
        ("workspace/AGENTS.md", "rules"),
    ],
)
def test_execute_reports_allowed_state_change(tmp_path, monkeypatch, logical, component):
    source = tmp_path / "context"
    path = source.joinpath(*logical.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Synthetic initial state", encoding="utf-8")
    replica = _replica(
        tmp_path,
        monkeypatch,
        mode="selected",
        files=[logical],
        context_root=source,
    )

    async def fake_run(mode, prompt):
        _write_attestation(replica, mode)
        if mode == "preflight":
            return 86, b"", b""
        replica._replica_files()[logical].write_text(
            "Synthetic changed state", encoding="utf-8"
        )
        assert replica.tool_attempts_path is not None
        replica.tool_attempts_path.write_text("1", encoding="utf-8")
        return 0, b"Synthetic response", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    result = asyncio.run(
        replica.execute(
            "Synthetic prompt",
            1024,
            allowed_state_paths=frozenset({logical}),
            observe_tool_attempts=True,
        )
    )
    assert result.evidence is not None
    assert result.evidence.changed_components == (component,)
    assert result.evidence.tool_attempt_count == 1
    assert result.evidence.initial_state != result.evidence.final_state


def test_probe_counts_blocked_tool_attempts(tmp_path, monkeypatch):
    namespace = {}
    exec(_PROBE_SOURCE, namespace)
    path = tmp_path / "tool-attempts.txt"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("WALLBREAKER_HERMES_TOOL_ATTEMPTS", str(path))
    assert namespace["_block_tool_call"]()["action"] == "block"
    assert namespace["_block_tool_call"]()["action"] == "block"
    assert path.read_text(encoding="utf-8") == "1\n1\n"


def test_preflight_tool_attempt_fails_before_run(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    phases = []

    async def fake_run(mode, prompt):
        phases.append(mode)
        _write_attestation(replica, mode)
        assert replica.tool_attempts_path is not None
        replica.tool_attempts_path.write_text("1\n", encoding="utf-8")
        return 86, b"", b""

    monkeypatch.setattr(replica, "_run_process", fake_run)
    with pytest.raises(ProviderError, match="preflight.*tool"):
        asyncio.run(replica.execute("Synthetic prompt", 1024))
    assert phases == ["preflight"]


def test_invalid_tool_attempt_evidence_fails_closed(tmp_path, monkeypatch):
    replica = _replica(tmp_path, monkeypatch)
    replica.prepare(1024)
    assert replica.tool_attempts_path is not None
    replica.tool_attempts_path.write_text("invalid", encoding="utf-8")
    with pytest.raises(ProviderError, match="tool-attempt evidence"):
        replica._read_tool_attempts()
    asyncio.run(replica.close())


def test_query_target_rejects_blocked_hermes_features_before_provider(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    endpoint = _endpoint(tmp_path, manifest)
    config = Config(default_profile="brain", profiles={}, target=endpoint)
    context = ToolContext(config=config)
    result = asyncio.run(_query_target({"prompt": "x", "system": "blocked"}, context))
    assert result == "Error: Hermes laboratory targets do not support system."
    continued = asyncio.run(_continue_target({"prompt": "x"}, context))
    assert continued == "Error: Hermes laboratory targets support one user turn only."


def test_breakvault_defaults_off_for_hermes(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    endpoint = _endpoint(tmp_path, manifest)
    config = Config(default_profile="brain", profiles={}, target=endpoint)
    assert ToolContext(config=config).vault_enabled is False


def test_hermes_tui_disables_logs_and_autosave(tmp_path, monkeypatch):
    from wallbreaker.prompts import DEFAULT_SYSTEM
    from wallbreaker.tui.app import RthApp
    import wallbreaker.session as session

    manifest = _manifest(tmp_path / "manifest.json")
    target = _endpoint(tmp_path, manifest)
    brain = Endpoint("brain", "openai", "http://fixture", "fixture/brain")
    config = Config(default_profile="brain", profiles={"brain": brain}, target=target)
    autosave = tmp_path / "autosave.json"
    monkeypatch.setattr(session, "autosave_path", lambda directory="sessions": autosave)
    app = RthApp(config, brain, DEFAULT_SYSTEM, prefs={"log": True})
    app.history = [user("Synthetic prompt")]
    app._autosave()
    assert app.runlog.enabled is False
    assert not autosave.exists()


def test_finish_does_not_persist_hermes_artifacts(tmp_path):
    manifest = _manifest(tmp_path / "manifest.json")
    endpoint = _endpoint(tmp_path, manifest)
    context = ToolContext(
        config=Config(default_profile="brain", profiles={}, target=endpoint),
        cwd=str(tmp_path),
    )
    result = asyncio.run(_finish({"summary": "Synthetic finding"}, context))
    assert result == "Engagement complete. Shutting down the harness."
    assert not (tmp_path / "wb_runs").exists()


def test_dashboard_does_not_persist_hermes_run(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from wallbreaker.dashboard.server import create_app
    from wallbreaker.tools.registry import ToolResult
    import wallbreaker.tools as tools

    manifest = _manifest(tmp_path / "manifest.json")
    target = _endpoint(tmp_path, manifest)
    brain = Endpoint("brain", "openai", "http://fixture", "fixture/brain")
    config = Config(
        default_profile="brain",
        profiles={"brain": brain},
        target=target,
        path=tmp_path / "config.toml",
    )

    class FakeRegistry:
        async def execute(self, name, args):
            return ToolResult("Synthetic response")

    monkeypatch.setattr(tools, "build_registry", lambda _config: FakeRegistry())
    sessions = tmp_path / "sessions"
    client = TestClient(
        create_app(config=config, sessions_dir=sessions, require_auth=False)
    )
    response = client.post("/api/fire", json={"request": "Synthetic prompt"})
    assert response.status_code == 200
    assert response.json()["run_log"] == ""
    assert not list(sessions.glob("run-*.jsonl"))


def test_dashboard_v2_succeeds_without_hermes_run_log(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from wallbreaker.dashboard.server import create_app
    from wallbreaker.tools.registry import ToolResult
    import wallbreaker.tools as tools

    manifest = _manifest(tmp_path / "manifest.json")
    target = _endpoint(tmp_path, manifest)
    brain = Endpoint("brain", "openai", "http://fixture", "fixture/brain")
    config = Config(
        default_profile="brain",
        profiles={"brain": brain},
        target=target,
        path=tmp_path / "config.toml",
    )

    class FakeRegistry:
        tools = {"query_target": object()}

        def __init__(self):
            self.ctx = SimpleNamespace()

        def names(self):
            return list(self.tools)

        async def execute(self, name, args):
            return ToolResult("Synthetic response")

    monkeypatch.setattr(
        tools,
        "build_registry",
        lambda _config, cwd=".": FakeRegistry(),
    )
    sessions = tmp_path / "sessions"
    with TestClient(
        create_app(config=config, sessions_dir=sessions, require_auth=False)
    ) as client:
        created = client.post(
            "/api/v2/executions",
            json={
                "capability_id": "tool.query_target",
                "args": {"prompt": "Synthetic prompt"},
            },
        )
        assert created.status_code == 200
        execution_id = created.json()["id"]
        execution = None
        for _ in range(50):
            execution = client.get(f"/api/v2/executions/{execution_id}").json()
            if execution["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.01)
    assert execution is not None
    assert execution["status"] == "succeeded", execution["error"]
    assert execution["result"]["run_log"] == ""
    assert not list(sessions.glob("run-*.jsonl"))


def test_breakvault_default_tolerates_minimal_config_doubles():
    assert ToolContext(config=cast(Config, None)).vault_enabled is True
    assert ToolContext(config=cast(Config, SimpleNamespace())).vault_enabled is True


def test_fixed_baseline_sha_is_full_length():
    assert len(HERMES_BASELINE_SHA) == 40
