"""Run from repository root: uv run --project backend python -m backend.profiling."""

import argparse
from pathlib import Path

from backend.profiling.runner import profile_dataset, write_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile source CSVs without modifying them"
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/reports"))
    parser.add_argument("--memory-mb", type=int, default=1024)
    args = parser.parse_args(argv)
    raw, destination = args.raw_dir.resolve(), args.report_dir.resolve()
    if destination == raw or destination.is_relative_to(raw):
        parser.error("reports must be outside the raw source directory")
    if args.memory_mb < 64:
        parser.error("--memory-mb must be at least 64")
    report = profile_dataset(raw, memory_mb=args.memory_mb)
    write_reports(report, destination)
    total = report.get("deal_total", "unavailable")
    print(
        f"Profile {report['status']}; deal rows: {total}; "
        f"issues: {len(report['issues'])}"
    )
    print(f"Reports: {destination / 'profile.json'} and {destination / 'profile.md'}")
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
