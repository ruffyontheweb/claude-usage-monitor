#!/usr/bin/env python3
"""Re-measure the handoff floor from recent transcripts. Read-only: prints a report, never edits the config.

Usage: remeasure.py [--days 14] [--projects-dir ~/.claude/projects]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from handoff_lib import CONFIG_PATH, STATE_DIR, fmt_tokens, load_config, usage_size  # noqa: E402

CANDIDATES = [100_000, 150_000, 200_000, 300_000]
MIN_SHARE = 0.80


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round(p * len(sorted_vals) + 0.5)) - 1))
    return sorted_vals[k]


def _share_above(sizes, threshold):
    total = sum(sizes)
    return sum(s for s in sizes if s >= threshold) / total if total else 0.0


def analyse(projects_dir: Path, days: float = 14, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    per_model: dict[str, dict] = {}
    seen: set[str] = set()
    for path in sorted(Path(projects_dir).glob("**/*.jsonl")):
        try:
            if path.stat().st_mtime < cutoff:
                continue
            f = open(path, "rb")
        except OSError:
            continue
        last_model = None
        with f:
            for raw in f:
                if b"compact" not in raw and b'"usage"' not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(obj, dict) or obj.get("isSidechain") is True:
                    continue
                if obj.get("isCompactSummary") or obj.get("subtype") == "compact_boundary":
                    if last_model:
                        per_model[last_model]["compactions"] += 1
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage")
                model = msg.get("model")
                if not isinstance(usage, dict) or not model or model.startswith("<"):
                    continue
                mid = msg.get("id")
                if mid:
                    if mid in seen:
                        continue
                    seen.add(mid)
                size = usage_size(usage)
                if size <= 0:
                    continue
                m = per_model.setdefault(model, {"sizes": [], "compactions": 0, "versions": set()})
                m["sizes"].append(size)
                if obj.get("version"):
                    m["versions"].add(obj["version"])
                last_model = model

    models = {}
    pooled = []
    for name, m in sorted(per_model.items()):
        sizes = sorted(m["sizes"])
        pooled.extend(sizes)
        models[name] = {
            "requests": len(sizes), "p50": _percentile(sizes, 0.5), "p90": _percentile(sizes, 0.9),
            "max": sizes[-1], "compactions": m["compactions"], "versions": sorted(m["versions"]),
            "share_above": {t: _share_above(sizes, t) for t in CANDIDATES},
        }
    pooled_share = {t: _share_above(pooled, t) for t in CANDIDATES}
    fits = [t for t in CANDIDATES if pooled_share[t] >= MIN_SHARE]
    return {"models": models, "pooled_share_above": pooled_share,
            "suggested_floor": max(fits) if fits else None, "windows": _windows_seen()}


def _windows_seen() -> dict:
    windows: dict[str, set] = {}
    for p in STATE_DIR.glob("*.json") if STATE_DIR.is_dir() else []:
        try:
            s = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(s, dict) and s.get("context_window"):
            windows.setdefault(s.get("model_id") or "?", set()).add(int(s["context_window"]))
    return {k: sorted(v) for k, v in windows.items()}


def print_report(report: dict, config: dict, days: float) -> None:
    print(f"Main-session requests in transcripts modified in the last {days:g} days")
    for name, m in report["models"].items():
        print(f"\n{name}: {m['requests']} requests, context p50 {fmt_tokens(m['p50'])}, "
              f"p90 {fmt_tokens(m['p90'])}, max {fmt_tokens(m['max'])}; compactions {m['compactions']}; "
              f"Claude Code {', '.join(m['versions']) or '?'}")
        print("  share of tokens from requests at or above: " + ", ".join(
            f"{fmt_tokens(t)} {m['share_above'][t]:.2f}" for t in CANDIDATES))
    print("\nall models: share of tokens from requests at or above: " + ", ".join(
        f"{fmt_tokens(t)} {report['pooled_share_above'][t]:.2f}" for t in CANDIDATES))
    floor = report["suggested_floor"]
    print(f"suggested floor: {fmt_tokens(floor) if floor else 'none'} (largest candidate with share >= "
          f"{MIN_SHARE:.2f}); current {fmt_tokens(config['floor_tokens'])}")
    largest = max((m["max"] for m in report["models"].values()), default=0)
    windows = "; ".join(f"{k} {', '.join(fmt_tokens(w) for w in v)}" for k, v in report["windows"].items()) or "none recorded"
    print(f"suggested near_full_fraction: {config['near_full_fraction']} (unchanged); largest context seen "
          f"{fmt_tokens(largest)}; windows recorded: {windows}")
    print("config not changed; edit config/handoff.json to apply")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=14)
    ap.add_argument("--projects-dir", type=Path, default=Path.home() / ".claude" / "projects")
    args = ap.parse_args(argv)
    print_report(analyse(args.projects_dir, args.days), load_config(), args.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
