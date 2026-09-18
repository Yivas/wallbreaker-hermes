from __future__ import annotations

from ..config import Config
from .registry import Tool, ToolContext, ToolRegistry


# The tools that actually attack or grade: fire, keep the thread, transform, mutate, judge, look
# for a seed. Mounting the full registry instead puts ~80 tool schemas in the attacker's system
# prompt, which costs tens of thousands of tokens per round and blurs the model's focus.
CORE_ATTACK_TOOLS = (
    "target", "multi_fire", "diff_fire", "prefill", "narrate", "pair", "mutate",
    "parseltongue", "parsel_engine", "judge", "judge_selftest", "recommend",
    "recommend_next", "leak_scan", "session_card", "strategy_attack",
)


def build_registry(config: Config, cwd: str | None = None, tools: str = "all") -> ToolRegistry:
    judge_endpoint = config.judge if getattr(config, "judge_enabled", True) else None
    if judge_endpoint is None and getattr(config, "judge_enabled", True):
        try:
            judge_endpoint = config.profile()
        except Exception:
            judge_endpoint = None
    ctx = ToolContext(config=config, cwd=cwd or ".", judge_endpoint=judge_endpoint)
    registry = ToolRegistry(ctx)

    from . import control, files, shell

    if tools == "core":
        for module_name in CORE_ATTACK_TOOLS:
            try:
                module = __import__(f"{__name__}.{module_name}", fromlist=["register"])
            except ImportError:
                continue
            module.register(registry)
        control.register(registry)
        return registry

    shell.register(registry)
    files.register(registry)
    control.register(registry)

    for module_name in (
        "parseltongue", "parsel_engine", "l1b3rt4s", "gemlib", "eni", "system_prompts", "target", "http_tool", "judge", "multi_fire",
        "crescendo", "optimize", "presets_tool", "mutate", "barcode_tool",
        "pair", "best_of_n", "many_shot", "prefill", "narrate", "diff_fire", "recommend",
        "campaign", "leaderboard", "leak_scan", "judge_selftest", "seed_sweep",
        "adapt_seed", "fire_file", "scan", "indirect_inject", "system_sweep",
        "harmbench_tool", "validate", "image", "image_edit", "st3gg",
        "goat", "tree_attack", "strategy_attack", "transfer_sweep",
        "cluster_findings",
        "typographic", "session_card", "rag_poison", "memory_poison", "agentharm", "fingerprint_defense",
        "profile_target", "recommend_next",
        "cot_forge",
        "deep_think_probe", "stolen_thoughts", "reasoning_hygiene",
        "evolve_persona", "framing_sweep", "persona_modulate", "author_persona",
        "persona_forge",
        "narrative_persona_splinter",
        "chat_template", "chat_session",
        "cipherchat", "skeleton_key", "persuasion_attack", "drattack", "ica",
        "vault", "swarm",
    ):
        try:
            module = __import__(f"{__name__}.{module_name}", fromlist=["register"])
        except ImportError:
            continue
        module.register(registry)
    return registry


__all__ = ["Tool", "ToolContext", "ToolRegistry", "build_registry"]
