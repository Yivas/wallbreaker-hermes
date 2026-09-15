"""Interactive private review of pending Hermes campaign attempts.

The report keeps the campaign sanitized; the bodies live in the private sidecar and
must stay on the operator's local terminal. This module reads them through the same
functions the CLI review commands use, shows one attempt at a time next to the case
expectation and the automatic signals, and stores decisions only when the operator
confirms them with the same ``apply_reviews`` call.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from rich.text import Text

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

Loader = Callable[[str | Path], "tuple[list[str], dict[str, dict], dict[str, dict]]"]
Storer = Callable[[str | Path, Mapping[str, str]], Any]


def safe_terminal_text(value: object) -> str:
    """Normalise line breaks and render remaining control characters visibly."""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub(lambda match: f"\\x{ord(match.group()):02x}", text)


def attempt_signals(fire: Mapping[str, Any] | None) -> dict:
    """Summarise what the report already knows about one fire."""
    if not fire:
        return {}
    behavior = fire.get("behavior") or {}
    state = fire.get("state") or {}
    tools = fire.get("tools") or {}
    return {
        "expected": behavior.get("expected"),
        "expected_state": state.get("expected"),
        "judge": behavior.get("judge_label"),
        "judge_status": behavior.get("judge_status"),
        "heuristic": behavior.get("heuristic_label"),
        "state": state.get("assessment"),
        "changed": list(state.get("changed_components") or ()),
        "tools": tools.get("attempt_count"),
    }


def describe_signals(signals: Mapping[str, Any]) -> str:
    """One line the operator can read before deciding."""
    if not signals:
        return "no automatic signals: read the objective and the response"
    judge = signals.get("judge") or signals.get("judge_status") or "sin juez"
    line = (
        f"expected {signals.get('expected')} | state {signals.get('expected_state')} | "
        f"judge {judge} | heuristic {signals.get('heuristic')} | "
        f"state check {signals.get('state')} | tools {signals.get('tools')}"
    )
    if signals.get("changed"):
        line += f" | changed {','.join(signals['changed'])}"
    return line


def load_pending(
    report_path: str | Path,
) -> tuple[list[str], dict[str, dict], dict[str, dict]]:
    """Return pending attempt ids, their private bodies and their report signals."""
    from .hermes_campaign import (
        load_campaign_evidence,
        load_campaign_report,
        private_review_entries,
    )

    report = load_campaign_report(report_path)
    evidence = load_campaign_evidence(report_path, report)
    entries = {
        entry["attempt_id"]: dict(entry)
        for entry in private_review_entries(report, evidence)
    }
    pending: list[str] = []
    signals: dict[str, dict] = {}
    for repetition in report["repetitions"]:
        attempt = repetition["attempts"][-1]
        if attempt["status"] != "review_required":
            continue
        pending.append(attempt["id"])
        fires = attempt.get("fires") or []
        signals[attempt["id"]] = attempt_signals(fires[0] if fires else None)
    return pending, entries, signals


def store_decisions(report_path: str | Path, decisions: Mapping[str, str]) -> Any:
    from .hermes_campaign import apply_reviews

    return apply_reviews(report_path, dict(decisions))


def build_review_app(
    report_path: str | Path,
    *,
    load: Loader = load_pending,
    store: Storer = store_decisions,
):
    """Build the Textual app; the loader and storer are injectable for tests."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, VerticalScroll
    from textual.widgets import Footer, Header, OptionList, Static
    from textual.widgets.option_list import Option

    class ReviewApp(App):
        """Pass or flag each pending attempt; nothing is written until 'a'."""

        ENABLE_COMMAND_PALETTE = False
        CSS = """
        #row { height: 1fr; }
        #list { width: 40%; height: auto; border: solid $primary; }
        #detail { width: 60%; border: solid $primary; padding: 0 1; }
        #expected { height: auto; background: $panel; padding: 0 1; }
        #status { height: 1; background: $surface; }
        """
        BINDINGS = [
            Binding("p", "decide_pass", "Pass", priority=True),
            Binding("f", "decide_finding", "Finding", priority=True),
            Binding("a", "apply", "Aplicar", priority=True),
            Binding("r", "reload", "Recargar", priority=True),
            Binding("q", "quit", "Salir", priority=True),
        ]

        def __init__(self, campaign_report: str | Path) -> None:
            super().__init__()
            self.campaign_report = campaign_report
            self.decisions: dict[str, str] = {}
            self.entries: dict[str, dict] = {}
            self.signals: dict[str, dict] = {}
            self.pending: list[str] = []
            self.current: str | None = None
            self.header_text = ""
            self.body_text = ""
            self.status_text = ""

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static(Text(""), id="expected")
            with Horizontal(id="row"):
                yield OptionList(id="list")
                with VerticalScroll(id="detail"):
                    yield Static(Text("Cargando."), id="body")
            yield Static(Text(""), id="status")
            yield Footer()

        def on_mount(self) -> None:
            self.title = "Wallbreaker Hermes: private review"
            self.sub_title = str(self.campaign_report)
            self.watch(self.query_one(OptionList), "highlighted", self.on_highlight)
            self.refresh_state()

        # -- state ---------------------------------------------------------
        def refresh_state(self) -> None:
            self.pending, self.entries, self.signals = load(self.campaign_report)
            self.current = self.pending[0] if self.pending else None
            self.rebuild_options()
            self.show_attempt()
            self.update_status()

        def summary_line(self, attempt_id: str) -> str:
            objective = safe_terminal_text(
                self.entries.get(attempt_id, {}).get("objective", "")
            )
            lines = [line for line in objective.splitlines() if line.strip()]
            return (lines[0] if lines else "sin objetivo")[:58]

        def rebuild_options(self) -> None:
            view = self.query_one(OptionList)
            view.clear_options()
            view.add_options(
                Option(
                    Text(
                        f"[{self.decisions.get(attempt_id, ' ')}] {index}. "
                        f"{self.summary_line(attempt_id)}"
                    ),
                    id=attempt_id,
                )
                for index, attempt_id in enumerate(self.pending, start=1)
            )
            if self.current in self.pending:
                view.highlighted = self.pending.index(self.current)
            elif self.pending:
                view.highlighted = 0
                self.current = self.pending[0]

        def on_highlight(self, index: int | None) -> None:
            if index is None or not 0 <= index < len(self.pending):
                return
            self.current = self.pending[index]
            self.show_attempt()

        def show_attempt(self) -> None:
            header = self.query_one("#expected", Static)
            body = self.query_one("#body", Static)
            if not self.current:
                self.header_text = "No pending attempts."
                self.body_text = "Press r to reload or q to quit."
                header.update(Text(self.header_text))
                body.update(Text(self.body_text))
                return
            self.header_text = describe_signals(self.signals.get(self.current, {}))
            header.update(Text(self.header_text))
            entry = self.entries.get(self.current, {})
            self.body_text = "\n".join(
                (
                    f"attempt {self.current}  fire {int(entry.get('fire_index', 0)) + 1}",
                    "",
                    "Objective",
                    safe_terminal_text(entry.get("objective", "")),
                    "",
                    "Prompt",
                    safe_terminal_text(entry.get("prompt", "")),
                    "",
                    "Response",
                    safe_terminal_text(entry.get("response", "")),
                )
            )
            body.update(Text(self.body_text))
            self.query_one("#detail").scroll_home(animate=False)

        def update_status(self) -> None:
            self.status_text = (
                f"pending {len(self.pending)}   marked {len(self.decisions)}"
            )
            self.query_one("#status", Static).update(Text(self.status_text))

        # -- actions -------------------------------------------------------
        def set_decision(self, value: str) -> None:
            if not self.current:
                self.notify("No attempt selected")
                return
            attempt_id = self.current
            self.decisions[attempt_id] = value
            index = self.pending.index(attempt_id)
            if index + 1 < len(self.pending):
                self.current = self.pending[index + 1]
            self.rebuild_options()
            self.show_attempt()
            self.update_status()
            self.notify(f"{attempt_id[:12]} = {value}")

        def action_decide_pass(self) -> None:
            self.set_decision("pass")

        def action_decide_finding(self) -> None:
            self.set_decision("finding")

        def action_apply(self) -> None:
            if not self.decisions:
                self.notify("Nothing to apply")
                return
            try:
                store(self.campaign_report, dict(self.decisions))
            except Exception as error:  # surfaced in the UI, not swallowed
                self.notify(
                    f"Error: {type(error).__name__}", severity="error", timeout=10
                )
                return
            applied = len(self.decisions)
            self.decisions.clear()
            self.refresh_state()
            self.notify(f"{applied} decisions applied")

        def action_reload(self) -> None:
            self.refresh_state()

    return ReviewApp(report_path)


def run_review(report_path: str | Path, **kwargs) -> int:
    """Open the interactive review for one campaign report."""
    build_review_app(report_path, **kwargs).run()
    return 0
