from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .analyzer import analyze_episode, normalize_skill
from .git_tools import collect_git_snapshot, discover_repo
from .memory_files import append_skill_to_memory_files
from .store import MemoryStore, make_episode, utc_now


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
        description="Self improving repo memory for Codex and Claude Code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize .memorygrad in a repo.")
    init.add_argument("--repo", default=".", help="Target repo path.")
    init.set_defaults(func=cmd_init)

    watch = sub.add_parser("watch", help="Record an episode and propose repo-memory skills.")
    watch.add_argument("--repo", default=".", help="Target repo path.")
    watch.add_argument("--task", default="", help="Task or intent for this coding episode.")
    watch.add_argument("--agent", default="unknown", choices=["unknown", "codex", "claude"], help="Agent label.")
    watch.add_argument("--terminal-log", default="", help="Path to terminal/session log. Use '-' for stdin.")
    watch.add_argument("--max-terminal-bytes", type=int, default=80_000, help="Maximum terminal-log bytes to ingest.")
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
    review.set_defaults(func=cmd_review)

    status = sub.add_parser("status", help="Show MemoryGrad episode and proposal counts.")
    status.add_argument("--repo", default=".", help="Target repo path.")
    status.set_defaults(func=cmd_status)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    store.init()
    print(f"Initialized MemoryGrad in {store.root}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    if args.follow and args.once:
        print("Use either --once or --follow, not both.", file=sys.stderr)
        return 2

    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    store.init()

    if args.follow:
        print(f"Watching {repo} every {args.interval:g}s. Press Ctrl-C to stop.")
        last_fingerprint = ""
        while True:
            fingerprint = _snapshot_fingerprint(repo, args.terminal_log)
            if fingerprint != last_fingerprint:
                _watch_once(args, repo, store)
                last_fingerprint = fingerprint
            time.sleep(args.interval)

    return _watch_once(args, repo, store)


def cmd_review(args: argparse.Namespace) -> int:
    if args.accept_all and args.reject_all:
        print("Use either --accept-all or --reject-all, not both.", file=sys.stderr)
        return 2

    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    store.init()
    pending = store.list_proposals(status="pending")

    if not pending:
        print("No pending proposals.")
        return 0

    if args.accept_all:
        for proposal in pending:
            _accept_proposal(store, proposal)
        print(f"Accepted {len(pending)} proposal(s).")
        return 0

    if args.reject_all:
        for proposal in pending:
            _reject_proposal(store, proposal)
        print(f"Rejected {len(pending)} proposal(s).")
        return 0

    handled = 0
    for prefix in args.accept:
        proposal = _resolve_proposal(pending, prefix)
        _accept_proposal(store, proposal)
        handled += 1

    for prefix in args.reject:
        proposal = _resolve_proposal(pending, prefix)
        _reject_proposal(store, proposal)
        handled += 1

    if handled:
        print(f"Handled {handled} proposal(s).")
        return 0

    return _interactive_review(store, pending)


def cmd_status(args: argparse.Namespace) -> int:
    repo = discover_repo(Path(args.repo))
    store = MemoryStore(repo)
    store.init()
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
    return 0


def _watch_once(args: argparse.Namespace, repo: Path, store: MemoryStore) -> int:
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

    saved = []
    for draft in drafts:
        proposal = {
            **draft.to_dict(),
            "status": "pending",
            "created_at": utc_now(),
            "episode_id": episode["id"],
        }
        if store.save_proposal_if_new(proposal):
            saved.append(proposal)

    print(f"Recorded episode {episode['id']}")
    if not saved:
        print("No new proposals.")
        return 0

    for proposal in saved:
        print()
        print(f"Proposal {proposal['id']} ({proposal['confidence']:.0%} confidence)")
        print(f"Gradient: {proposal['text_gradient']}")
        print(f"Skill: {proposal['skill']}")
    print()
    print("Run `memorygrad review` to accept or reject.")
    return 0


def _interactive_review(store: MemoryStore, pending: list[dict[str, object]]) -> int:
    for proposal in pending:
        print()
        print(f"{proposal['id']}")
        print(f"Gradient: {proposal['text_gradient']}")
        print(f"Skill: {proposal['skill']}")
        for item in proposal.get("evidence", []):
            print(f"Evidence: {item}")

        while True:
            answer = input("Accept? [a]ccept/[r]eject/[s]kip/[q]uit: ").strip().lower()
            if answer in {"a", "accept"}:
                _accept_proposal(store, proposal)
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


def _accept_proposal(store: MemoryStore, proposal: dict[str, object]) -> None:
    accepted_at = utc_now()
    append_skill_to_memory_files(
        store.root,
        skill=str(proposal["skill"]),
        text_gradient=str(proposal["text_gradient"]),
        proposal_id=str(proposal["id"]),
        accepted_at=accepted_at,
    )
    proposal["status"] = "accepted"
    proposal["accepted_at"] = accepted_at
    store.save_proposal(proposal)


def _reject_proposal(store: MemoryStore, proposal: dict[str, object]) -> None:
    proposal["status"] = "rejected"
    proposal["rejected_at"] = utc_now()
    store.save_proposal(proposal)


def _resolve_proposal(pending: list[dict[str, object]], prefix: str) -> dict[str, object]:
    matches = [proposal for proposal in pending if str(proposal["id"]).startswith(prefix)]
    if not matches:
        raise SystemExit(f"No pending proposal matches {prefix!r}.")
    if len(matches) > 1:
        ids = ", ".join(str(proposal["id"]) for proposal in matches)
        raise SystemExit(f"Proposal prefix {prefix!r} is ambiguous: {ids}")
    return matches[0]


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
