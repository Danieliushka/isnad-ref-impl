"""
isnad.visualize — Text-based trust chain visualization.

Renders attestation chains as readable ASCII graphs for debugging,
auditing, and demo purposes.
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Sequence

from isnad.core import Attestation, TrustChain


def render_chain(
    chain: TrustChain,
    *,
    scope: Optional[str] = None,
    show_scores: bool = True,
    show_timestamps: bool = False,
    max_width: int = 80,
) -> str:
    """
    Render the trust chain as a human-readable text graph.

    Example output::

        Trust Chain (6 attestations, 4 agents)
        ════════════════════════════════════════

        alice ──[code-review]──▶ bob          ✅ 0.20
        alice ──[code-review]──▶ bob          ✅ 0.10  (repeat witness)
        bob   ──[deploy]───────▶ charlie      ✅ 0.20
        carol ──[audit]────────▶ alice        ✅ 0.20

        Agent Scores:
          bob      0.30  ██████░░░░
          charlie  0.20  ████░░░░░░
          alice    0.20  ████░░░░░░

    Args:
        chain: TrustChain to visualize.
        scope: Optional scope filter for attestations.
        show_scores: Show per-attestation weight and agent scores.
        show_timestamps: Include timestamps on each attestation line.
        max_width: Maximum line width.

    Returns:
        Multi-line string with the rendered visualization.
    """
    attestations = chain.attestations
    if scope:
        attestations = [
            a for a in attestations if scope.lower() in a.task.lower()
        ]

    if not attestations:
        return "Trust Chain: (empty)\n"

    agents = _collect_agents(attestations)
    out = io.StringIO()

    # Header
    out.write(f"Trust Chain ({len(attestations)} attestations, {len(agents)} agents)\n")
    out.write("═" * min(max_width, 50) + "\n\n")

    # Attestation lines
    max_witness = max(len(a.witness) for a in attestations)
    max_subject = max(len(a.subject) for a in attestations)
    witness_counts: dict[str, int] = defaultdict(int)

    for att in attestations:
        witness_counts[att.witness] += 1
        repeat = witness_counts[att.witness] > 1 and any(
            prev.subject == att.subject and prev.witness == att.witness
            for prev in attestations[:attestations.index(att)]
        )

        sig_ok = att.verify()
        status = "✅" if sig_ok else "❌"

        witness_pad = att.witness.ljust(max_witness)
        task_label = _truncate(att.task, 20)
        arrow = f"──[{task_label}]──▶"

        line = f"  {witness_pad} {arrow} {att.subject}"

        if show_scores and sig_ok:
            weight = _attestation_weight(att, attestations)
            line += f"  {status} {weight:.2f}"
        else:
            line += f"  {status}"

        if repeat:
            line += "  (repeat witness)"

        if show_timestamps and att.timestamp:
            try:
                ts = datetime.fromisoformat(str(att.timestamp))
            except (ValueError, TypeError):
                ts = datetime.fromtimestamp(float(att.timestamp), tz=timezone.utc)
            line += f"  [{ts:%Y-%m-%d %H:%M}]"

        out.write(line + "\n")

    # Agent scores
    if show_scores:
        out.write("\n  Agent Scores:\n")
        scores = []
        for agent in sorted(agents):
            s = chain.trust_score(agent, scope=scope)
            scores.append((agent, s))
        scores.sort(key=lambda x: -x[1])

        max_name = max(len(name) for name, _ in scores) if scores else 0
        for name, score in scores:
            bar = _bar(score, width=10)
            out.write(f"    {name.ljust(max_name)}  {score:.2f}  {bar}\n")

    out.write("")
    return out.getvalue()


def render_graph(
    chain: TrustChain,
    *,
    scope: Optional[str] = None,
) -> str:
    """
    Render the trust chain as a DOT graph (Graphviz format).

    Can be piped to `dot -Tpng` for image output.
    """
    attestations = chain.attestations
    if scope:
        attestations = [
            a for a in attestations if scope.lower() in a.task.lower()
        ]

    out = io.StringIO()
    out.write("digraph isnad_trust {\n")
    out.write('  rankdir=LR;\n')
    out.write('  node [shape=box, style=rounded, fontname="monospace"];\n')
    out.write('  edge [fontname="monospace", fontsize=10];\n\n')

    # Nodes with scores
    agents = _collect_agents(attestations)
    for agent in sorted(agents):
        score = chain.trust_score(agent, scope=scope)
        color = _score_color(score)
        out.write(f'  "{agent}" [label="{agent}\\nscore: {score:.2f}", '
                  f'color="{color}", penwidth=2];\n')

    out.write("\n")

    # Edges
    for att in attestations:
        sig_ok = att.verify()
        style = "solid" if sig_ok else "dashed"
        color = "darkgreen" if sig_ok else "red"
        label = _truncate(att.task, 15)
        out.write(f'  "{att.witness}" -> "{att.subject}" '
                  f'[label="{label}", style={style}, color="{color}"];\n')

    out.write("}\n")
    return out.getvalue()


def render_agent_summary(
    chain: TrustChain,
    agent_id: str,
    *,
    scope: Optional[str] = None,
) -> str:
    """
    Render a summary card for a single agent.

    Example::

        Agent: bob
        ─────────────
        Trust Score: 0.40
        Attestations received: 3
        Attestations given:    1
        Unique witnesses:      2
        Top scope: code-review (2 attestations)
    """
    attestations_received = [
        a for a in chain.attestations if a.subject == agent_id
    ]
    attestations_given = [
        a for a in chain.attestations if a.witness == agent_id
    ]

    if scope:
        attestations_received = [
            a for a in attestations_received if scope.lower() in a.task.lower()
        ]
        attestations_given = [
            a for a in attestations_given if scope.lower() in a.task.lower()
        ]

    score = chain.trust_score(agent_id, scope=scope)
    unique_witnesses = len({a.witness for a in attestations_received})

    # Top scope
    scope_counts: dict[str, int] = defaultdict(int)
    for a in attestations_received:
        scope_counts[a.task] += 1
    top_scope = max(scope_counts.items(), key=lambda x: x[1]) if scope_counts else ("none", 0)

    out = io.StringIO()
    out.write(f"Agent: {agent_id}\n")
    out.write("─" * (len(agent_id) + 7) + "\n")
    out.write(f"  Trust Score:           {score:.2f}  {_bar(score, 10)}\n")
    out.write(f"  Attestations received: {len(attestations_received)}\n")
    out.write(f"  Attestations given:    {len(attestations_given)}\n")
    out.write(f"  Unique witnesses:      {unique_witnesses}\n")
    if scope_counts:
        out.write(f"  Top scope:             {top_scope[0]} ({top_scope[1]} attestations)\n")

    return out.getvalue()


# ─── Helpers ──────────────────────────────────────────────────────

def _collect_agents(attestations: Sequence[Attestation]) -> set[str]:
    agents: set[str] = set()
    for a in attestations:
        agents.add(a.subject)
        agents.add(a.witness)
    return agents


def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _score_color(score: float) -> str:
    if score >= 0.7:
        return "darkgreen"
    elif score >= 0.4:
        return "orange"
    else:
        return "red"


def _attestation_weight(
    att: Attestation, all_atts: Sequence[Attestation]
) -> float:
    """Approximate the weight this attestation contributes."""
    base = 0.2
    # Count how many times this witness attested this subject before this one
    count = 0
    for a in all_atts:
        if a is att:
            break
        if a.witness == att.witness and a.subject == att.subject:
            count += 1
    decay = 0.5 ** count
    return base * decay
