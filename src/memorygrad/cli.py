from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .analyzer import analyze_episode
from .config import (
    DEFAULT_MAX_ACTIVE_SKILLS,
    DEFAULT_MIN_CONFIDENCE,
    default_config,
    load_global_config,
    resolve_targets,
    save_global_config,
)
from .git_tools import collect_git_snapshot, discover_repo
from .memory_files import append_rejection_to_buffer, append_skill_to_memory_files, sync_memory_targets
from .store import MemoryStore, make_episode, utc_now


AGENT_CHOICES = ["unknown", "codex", "claude", "gemini", "copilot", "cursor", "other"]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memorygrad",
        description="Passive gradient memory for coding agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize .memorygrad in a repo.")
    init.add_argument("--repo", default=".", help="Target repo path.")
    init.add_argument(
        "--targets",
        default="core",
        help="Memory targets: core, auto, all, none, or comma-separated aliases/paths. Default: core.",
    )
    init.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE, help="Default proposal gate.")
    init.add_argument("--max-active-skills", type=int, default=DEFAULT_MAX_ACTIVE_SKILLS, help="Active memory cap.")
    init.set_defaults(func=cmd_init)

    start = sub.add_parser("start", help="One-time easy setup.")
    start.add_argument("--repo", default=None, help="Optional repo path for repo-local setup.")
    start.add_argument(
        "--targets",
        default="auto",
        help="Memory targets: auto, core, agents, all, none, or comma-separated aliases/paths. Default: auto.",
    )
    start.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE, help="Default proposal gate.")
    start.add_argument("--max-active-skills", type=int, default=DEFAULT_MAX_ACTIVE_SKILLS, help="Active memory cap.")
    start.set_defaults(func=cmd_start)

    learn = sub.add_parser("learn", help="Easy one-shot ingest for a coding session.")
    learn.add_argument("task", nargs="?", default="", help="What the agent was trying to do.")
    learn.add_argument("--repo", default=".", help="Target repo path.")
    learn.add_argument("--log", "--terminal-log", dest="terminal_log", default="", help="Terminal/session log path.")
    learn.add_argument("--agent", default="unknown", choices=AGENT_CHOICES, help="Agent label.")
    learn.add_argument("--max-terminal-bytes", type=int, default=80_000, help="Maximum log bytes to ingest.")
    learn.add_argument("--min-confidence", type=float, default=None, help="Override the configured proposal gate.")
    learn.add_argument("--review", action="store_true", help="Open interactive review after ingesting.")
    learn.add_argument("--accept-all", action="store_true", help="Accept high-confidence proposals after ingesting.")
    learn.set_defaults(func=cmd_learn)

    watch = sub.add_parser("watch", help="Record an episode and propose repo-memory skills.")
    watch.add_argument("--repo", default=".", help="Target repo path.")
    watch.add_argument("--task", default="", help="Task or intent for this coding episode.")
    watch.add_argument(
        "--agent",
        default="unknown",
        choices=AGENT_CHOICES,
        help="Agent label.",
    )
    watch.add_argument("--terminal-log", default="", help="Path to terminal/session log. Use '-' for stdin.")
    watch.add_argument("--max-terminal-bytes", type=int, default=80_000, help="Maximum terminal-log bytes to ingest.")
    watch.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Only save proposals at or above this confidence. Default comes from .memorygrad/config.json.",
    )
    watch.add_argument("--once", action="store_true", help="Record one snapshot and exit.")
    watch.add_argument("--follow", action="store_true", help="Keep polling until interrupted.")
    watch.add_argument("--interval", type=float, default=10.0, help="Polling interval for --follow.")
    watch.set_defaults(func=cmd_watch)

    review = sub.add_parser("review", help="Review pending MemoryGrad proposals.")
    review.add_argument("--repo", default=".", help="Target repo path.")
    review.add_argument("--accept-all", action="store_true", help="Accept every pending proposal.")
    review.add_argument("--reject-all", action="store_true", help="Reject every pending proposal.")
    review.add_argument("--accept", action="append", default=[], help="Accept a proposal id or id prefix.")
    review.add_argument("--reject", action="append", default=[], help="Reject a proposal id or id prefix.")
    review.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Minimum confidence for accepting proposals unless --force is used.",
    )
    review.add_argument("--targets", default=None, help="Override configured sync targets for accepted proposals.")
    review.add_argument("--max-active-skills", type=int, default=None, help="Override configured active memory cap.")
    review.add_argument("--force", action="store_true", help="Allow accepting proposals below --min-confidence.")
    review.set_defaults(func=cmd_review)

    sync = sub.add_parser("sync", help="Rewrite configured agent memory files from accepted skills.")
    sync.add_argument("--repo", default=".", help="Target repo path.")
    sync.add_argument("--targets", default=None, help="Override configured sync targets.")
    sync.add_argument("--max-active-skills", type=int, default=None, help="Override configured active memory cap.")
    sync.set_defaults(func=cmd_sync)

    status = sub.add_parser("status", help="Show MemoryGrad episode and proposal counts.")
    status.add_argument("--repo", default=".", help="Target repo path.")
    status.set_defaults(func=cmd_status)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    return _initialize_repo(
        repo,
        targets=args.targets,
        min_confidence=args.min_confidence,
        max_active_skills=args.max_active_skills,
    )


def cmd_start(args: argparse.Namespace) -> int:
    if args.repo is None:
        if not _valid_confidence(args.min_confidence):
            print("--min-confidence must be between 0 and 1.", file=sys.stderr)
            return 2
        if args.max_active_skills < 1:
            print("--max-active-skills must be at least 1.", file=sys.stderr)
            return 2

        config = default_config(targets=resolve_targets(Path.cwd(), args.targets))
        config["min_confidence"] = args.min_confidence
        config["max_active_skills"] = args.max_active_skills
        path = save_global_config(config)
        print(f"Started MemoryGrad globally at {path.parent}")
        print(f"Default targets: {', '.join(config['targets']) or '(none)'}")
        print(f"Memory gate: {config['min_confidence']:.0%}; active cap: {config['max_active_skills']}")
        print()
        print("In any git repo after an agent run:")
        print('  memorygrad learn "what the agent tried" --log session.log')
        print("  memorygrad review")
        return 0

    repo = discover_repo(Path(args.repo))
    result = _initialize_repo(
        repo,
        targets=args.targets,
        min_confidence=args.min_confidence,
        max_active_skills=args.max_active_skills,
    )
    if result == 0:
        print()
        print("Next:")
        print('  memorygrad learn "what the agent tried" --log session.log')
        print("  memorygrad review")
    return result


def cmd_learn(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    store = _ensure_repo_started(repo)
    config = store.load_config()
    min_confidence = _effective_confidence(args.min_confidence, config)
    if not _valid_confidence(min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2

    result = _watch_once(args, repo, store, min_confidence=min_confidence)
    if result != 0 or not (args.review or args.accept_all):
        return result

    review_args = argparse.Namespace(
        repo=str(repo),
        accept_all=args.accept_all,
        reject_all=False,
        accept=[],
        reject=[],
        min_confidence=args.min_confidence,
        targets=None,
        max_active_skills=None,
        force=False,
    )
    return cmd_review(review_args)


def cmd_watch(args: argparse.Namespace) -> int:
    if args.follow and args.once:
        print("Use either --once or --follow, not both.", file=sys.stderr)
        return 2
    if not _valid_confidence(args.min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2

    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    store.init()
    config = store.load_config()
    min_confidence = _effective_confidence(args.min_confidence, config)
    if not _valid_confidence(min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2

    if args.follow:
        print(f"Watching {repo} every {args.interval:g}s. Press Ctrl-C to stop.")
        last_fingerprint = ""
        while True:
            fingerprint = _snapshot_fingerprint(repo, args.terminal_log)
            if fingerprint != last_fingerprint:
                _watch_once(args, repo, store, min_confidence=min_confidence)
                last_fingerprint = fingerprint
            time.sleep(args.interval)

    return _watch_once(args, repo, store, min_confidence=min_confidence)


def cmd_review(args: argparse.Namespace) -> int:
    if args.accept_all and args.reject_all:
        print("Use either --accept-all or --reject-all, not both.", file=sys.stderr)
        return 2
    if not _valid_confidence(args.min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2

    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    config = store.load_config()
    min_confidence = _effective_confidence(args.min_confidence, config)
    max_active_skills = _effective_max_active(args.max_active_skills, config)
    target_paths = _effective_targets(args.targets, repo, config)
    if not _valid_confidence(min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2
    if max_active_skills < 1:
        print("--max-active-skills must be at least 1.", file=sys.stderr)
        return 2
    pending = store.list_proposals(status="pending")

    if not pending:
        print("No pending proposals.")
        return 0

    if args.accept_all:
        eligible, skipped = _split_by_confidence(pending, min_confidence, args.force)
        for proposal in eligible:
            _accept_proposal(store, proposal, target_paths=target_paths, max_active_skills=max_active_skills)
        print(f"Accepted {len(eligible)} proposal(s).")
        if skipped:
            print(f"Skipped {len(skipped)} below-threshold proposal(s); use --force to accept them.")
        return 0

    if args.reject_all:
        for proposal in pending:
            _reject_proposal(store, proposal)
        print(f"Rejected {len(pending)} proposal(s).")
        return 0

    handled = 0
    for prefix in args.accept:
        proposal = _resolve_proposal(pending, prefix)
        _require_acceptable(proposal, min_confidence, args.force)
        _accept_proposal(store, proposal, target_paths=target_paths, max_active_skills=max_active_skills)
        handled += 1

    for prefix in args.reject:
        proposal = _resolve_proposal(pending, prefix)
        _reject_proposal(store, proposal)
        handled += 1

    if handled:
        print(f"Handled {handled} proposal(s).")
        return 0

    return _interactive_review(
        store,
        pending,
        min_confidence=min_confidence,
        force=args.force,
        target_paths=target_paths,
        max_active_skills=max_active_skills,
    )


def cmd_status(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    config = store.load_config()
    episodes = store.list_episodes()
    proposals = store.list_proposals()
    counts: dict[str, int] = {}
    for proposal in proposals:
        status = str(proposal.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1

    print(f"Repo: {repo}")
    print(f"Episodes: {len(episodes)}")
    print(f"Proposals: {len(proposals)}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print(f"Memory gate: {float(config['min_confidence']):.0%}")
    print(f"Active cap: {config['max_active_skills']}")
    print(f"Targets: {', '.join(config['targets']) or '(none)'}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    config = store.load_config()
    max_active_skills = _effective_max_active(args.max_active_skills, config)
    target_paths = _effective_targets(args.targets, repo, config)
    if max_active_skills < 1:
        print("--max-active-skills must be at least 1.", file=sys.stderr)
        return 2

    written = sync_memory_targets(
        repo,
        accepted_proposals=store.list_accepted_proposals(),
        target_paths=target_paths,
        max_active_skills=max_active_skills,
    )
    print(f"Synced {len(written)} target(s).")
    for path in written:
        print(f"  {path.relative_to(repo)}")
    return 0


def _initialize_repo(
    repo: Path,
    *,
    targets: str,
    min_confidence: float,
    max_active_skills: int,
) -> int:
    store = MemoryStore(repo)
    if not _valid_confidence(min_confidence):
        print("--min-confidence must be between 0 and 1.", file=sys.stderr)
        return 2
    if max_active_skills < 1:
        print("--max-active-skills must be at least 1.", file=sys.stderr)
        return 2

    config = default_config(targets=resolve_targets(repo, targets))
    config["min_confidence"] = min_confidence
    config["max_active_skills"] = max_active_skills
    store.init(config=config)
    print(f"Initialized MemoryGrad in {store.root}")
    print(f"Targets: {', '.join(config['targets']) or '(none)'}")
    print(f"Memory gate: {config['min_confidence']:.0%}; active cap: {config['max_active_skills']}")
    return 0


def _ensure_repo_started(repo: Path) -> MemoryStore:
    store = MemoryStore(repo)
    if store.config_path.exists():
        store.init()
        return store

    config = load_global_config()
    store.init(config=config)
    return store


def _watch_once(args: argparse.Namespace, repo: Path, store: MemoryStore, *, min_confidence: float) -> int:
    terminal_output = _read_terminal_output(args.terminal_log, args.max_terminal_bytes)
    episode = make_episode(
        repo=repo,
        task=args.task,
        agent=args.agent,
        terminal_output=terminal_output,
        git=collect_git_snapshot(repo),
    )
    store.save_episode(episode)

    existing_skills = store.load_skill_texts()
    existing_skills.extend(str(item.get("skill", "")) for item in store.list_proposals())
    drafts = analyze_episode(episode, existing_skills=existing_skills)
    eligible_drafts = [draft for draft in drafts if draft.confidence >= min_confidence]
    skipped_drafts = [draft for draft in drafts if draft.confidence < min_confidence]

    saved = []
    for draft in eligible_drafts:
        proposal = {
            **draft.to_dict(),
            "status": "pending",
            "created_at": utc_now(),
            "episode_id": episode["id"],
        }
        if store.save_proposal_if_new(proposal):
            saved.append(proposal)

    rejected = []
    for draft in skipped_drafts:
        rejected_at = utc_now()
        proposal = {
            **draft.to_dict(),
            "status": "rejected_low_confidence",
            "created_at": rejected_at,
            "episode_id": episode["id"],
            "rejected_at": rejected_at,
            "rejection_reason": f"below {min_confidence:.0%} confidence gate",
        }
        if store.save_proposal_if_new(proposal):
            append_rejection_to_buffer(
                store.root,
                proposal_id=str(proposal["id"]),
                skill=str(proposal["skill"]),
                reason=str(proposal["rejection_reason"]),
                rejected_at=rejected_at,
            )
            rejected.append(proposal)

    print(f"Recorded episode {episode['id']}")
    if rejected:
        print(
            f"Rejected {len(rejected)} low-signal draft(s) below "
            f"{min_confidence:.0%} confidence."
        )
    if not saved:
        print("No new high-signal proposals.")
        return 0

    for proposal in saved:
        print()
        print(f"Proposal {proposal['id']} ({proposal['confidence']:.0%} confidence)")
        print(f"Gradient: {proposal['text_gradient']}")
        print(f"Skill: {proposal['skill']}")
    print()
    print("Run `memorygrad review` to accept or reject.")
    return 0


def _interactive_review(
    store: MemoryStore,
    pending: list[dict[str, object]],
    *,
    min_confidence: float,
    force: bool,
    target_paths: list[str],
    max_active_skills: int,
) -> int:
    for proposal in pending:
        print()
        print(f"{proposal['id']} ({_proposal_confidence(proposal):.0%} confidence)")
        print(f"Gradient: {proposal['text_gradient']}")
        print(f"Skill: {proposal['skill']}")
        for item in proposal.get("evidence", []):
            print(f"Evidence: {item}")

        while True:
            answer = input("Accept? [a]ccept/[r]eject/[s]kip/[q]uit: ").strip().lower()
            if answer in {"a", "accept"}:
                if _proposal_confidence(proposal) < min_confidence and not force:
                    print(f"Skipped: below {min_confidence:.0%} confidence. Re-run with --force to accept.")
                    break
                _accept_proposal(store, proposal, target_paths=target_paths, max_active_skills=max_active_skills)
                print("Accepted.")
                break
            if answer in {"r", "reject"}:
                _reject_proposal(store, proposal)
                print("Rejected.")
                break
            if answer in {"s", "skip", ""}:
                print("Skipped.")
                break
            if answer in {"q", "quit"}:
                return 0
            print("Please enter a, r, s, or q.")
    return 0


def _accept_proposal(
    store: MemoryStore,
    proposal: dict[str, object],
    *,
    target_paths: list[str],
    max_active_skills: int,
) -> None:
    accepted_at = utc_now()
    proposal["status"] = "accepted"
    proposal["accepted_at"] = accepted_at
    store.save_proposal(proposal)
    append_skill_to_memory_files(
        store.root,
        skill=str(proposal["skill"]),
        text_gradient=str(proposal["text_gradient"]),
        proposal_id=str(proposal["id"]),
        accepted_at=accepted_at,
        accepted_proposals=store.list_accepted_proposals(),
        target_paths=target_paths,
        max_active_skills=max_active_skills,
    )


def _reject_proposal(store: MemoryStore, proposal: dict[str, object]) -> None:
    rejected_at = utc_now()
    proposal["status"] = "rejected"
    proposal["rejected_at"] = rejected_at
    proposal["rejection_reason"] = "user rejected"
    store.save_proposal(proposal)
    append_rejection_to_buffer(
        store.root,
        proposal_id=str(proposal["id"]),
        skill=str(proposal["skill"]),
        reason=str(proposal["rejection_reason"]),
        rejected_at=rejected_at,
    )


def _resolve_proposal(pending: list[dict[str, object]], prefix: str) -> dict[str, object]:
    matches = [proposal for proposal in pending if str(proposal["id"]).startswith(prefix)]
    if not matches:
        raise SystemExit(f"No pending proposal matches {prefix!r}.")
    if len(matches) > 1:
        ids = ", ".join(str(proposal["id"]) for proposal in matches)
        raise SystemExit(f"Proposal prefix {prefix!r} is ambiguous: {ids}")
    return matches[0]


def _split_by_confidence(
    proposals: list[dict[str, object]], min_confidence: float, force: bool
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if force:
        return proposals, []
    eligible = [proposal for proposal in proposals if _proposal_confidence(proposal) >= min_confidence]
    skipped = [proposal for proposal in proposals if _proposal_confidence(proposal) < min_confidence]
    return eligible, skipped


def _require_acceptable(proposal: dict[str, object], min_confidence: float, force: bool) -> None:
    confidence = _proposal_confidence(proposal)
    if confidence < min_confidence and not force:
        raise SystemExit(
            f"Proposal {proposal['id']} is below {min_confidence:.0%} confidence; use --force to accept it."
        )


def _proposal_confidence(proposal: dict[str, object]) -> float:
    try:
        return float(proposal.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _effective_confidence(value: float | None, config: dict[str, object]) -> float:
    if value is not None:
        return value
    return float(config.get("min_confidence", DEFAULT_MIN_CONFIDENCE))


def _effective_max_active(value: int | None, config: dict[str, object]) -> int:
    if value is not None:
        return value
    return int(config.get("max_active_skills", DEFAULT_MAX_ACTIVE_SKILLS))


def _effective_targets(value: str | None, repo: Path, config: dict[str, object]) -> list[str]:
    if value is not None:
        return resolve_targets(repo, value)
    configured = config.get("targets", [])
    return resolve_targets(repo, configured if isinstance(configured, list) else None)


def _valid_confidence(value: float | None) -> bool:
    if value is None:
        return True
    return 0.0 <= value <= 1.0


def _read_terminal_output(path: str, max_bytes: int) -> str:
    if not path:
        return ""
    if path == "-":
        data = sys.stdin.buffer.read(max_bytes + 1)
    else:
        data = Path(path).expanduser().read_bytes()[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _snapshot_fingerprint(repo: Path, terminal_log: str) -> str:
    snapshot = collect_git_snapshot(repo)
    payload = {
        "status": snapshot.get("status", ""),
        "head": snapshot.get("head", ""),
        "terminal_log_mtime": _mtime(terminal_log),
    }
    return json.dumps(payload, sort_keys=True)


def _mtime(path: str) -> float | None:
    if not path or path == "-":
        return None
    try:
        return Path(path).expanduser().stat().st_mtime
    except OSError:
        return None
