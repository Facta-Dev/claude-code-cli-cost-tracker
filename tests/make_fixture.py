#!/usr/bin/env python3
"""Generate the synthetic transcript fixture — deterministic, no network.

    python3 tests/make_fixture.py [projects_dir]

Every awkward shape the tracker must survive, on purpose:
  - repeated identical message.usage across content blocks of one response
    (thinking + text + tool_use) — the overcounting trap,
  - both cache TTLs in one session,
  - a mid-session model switch (pricing follows each turn's model),
  - an unpriced model (billed $0, counted, named),
  - a <synthetic> zero-usage line,
  - a nested subagent transcript billing to the parent session,
  - non-assistant lines with no usage, and a malformed line.

Sessions 'sessA'/'sessB' work in /Users/demo/repos/cost-lab (repo cost-lab).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PROJECTS = ROOT / "fixtures" / "projects"
CWD = "/Users/demo/repos/cost-lab"
DAY = "2026-10-30T"


def line(obj: dict) -> str:
    return json.dumps(obj)


def assistant(mid: str, model: str, usage: dict | None, ts: str, sidechain: bool = False) -> str:
    msg = {"id": mid, "model": model, "role": "assistant"}
    if usage is not None:
        msg["usage"] = usage
    return line(
        {
            "type": "assistant",
            "message": msg,
            "timestamp": DAY + ts,
            "cwd": CWD,
            "isSidechain": sidechain,
            "agentId": "agent-1" if sidechain else "",
        }
    )


def usage(full: dict) -> dict:
    return full | {"speed": 12.3, "service_tier": "cloud", "server_tool_use": {}}


def main(projects_dir: Path) -> None:
    (projects_dir / "-Users-demo-repos-cost-lab").mkdir(parents=True, exist_ok=True)
    slug = projects_dir / "-Users-demo-repos-cost-lab"

    # -- session A: the overcounting trap, TTL split, model switch, unpriced,
    #    synthetic and one malformed line ---------------------------------
    u1 = usage(
        {
            "input_tokens": 1_000_000,
            "output_tokens": 400_000,
            "cache_read_input_tokens": 30_000_000,
            "cache_creation_input_tokens": 1_000_000,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 500_000,
                "ephemeral_1h_input_tokens": 500_000,
            },
        }
    )
    a_lines = [
        line({"type": "user", "message": {"role": "user", "content": "hello"}}),
        assistant("msg_001", "glm-5.3-flash", u1, "09:00:00Z"),
        assistant("msg_001", "glm-5.3-flash", u1, "09:00:00Z"),  # duplicate block
        assistant("msg_001", "glm-5.3-flash", u1, "09:00:00Z"),  # duplicate block
        "not-json-at-all\n",
        assistant("msg_002", "glm-5.2", usage({"input_tokens": 500_000, "output_tokens": 200_000}), "09:00:10Z"),
        assistant("msg_003", "unknown-model-x", usage({"input_tokens": 700_000, "output_tokens": 100_000}), "09:00:20Z"),
        line({"type": "user", "message": {"role": "user", "content": "next"}}),
        assistant("msg_004", "<synthetic>", {"input_tokens": 0, "output_tokens": 0}, "09:00:30Z"),
    ]
    (slug / "sessA.jsonl").write_text("\n".join(a_lines) + "\n")

    # -- session B: a first-party Claude turn beside Ollama turns, and a
    #    subagent transcript billing to the parent session ----------------
    b_lines = [
        line({"type": "user", "message": {"role": "user", "content": "go"}}),
        assistant("msg_B1", "glm-5.3-flash", usage({"input_tokens": 2_000_000, "cache_read_input_tokens": 8_000_000, "output_tokens": 100_000}), "09:10:00Z"),
        assistant("msg_B2", "claude-sonnet-5", usage({"input_tokens": 1_000_000, "output_tokens": 100_000}), "09:10:10Z"),
    ]
    (slug / "sessB.jsonl").write_text("\n".join(b_lines) + "\n")

    sub = slug / "sessB" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "agent-1.jsonl").write_text(
        assistant("msg_SUB1", "glm-5.3-flash", usage({"input_tokens": 5_000_000}), "09:10:15Z", sidechain=True) + "\n"
    )
    print(projects_dir)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PROJECTS
    main(target)