from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .calibrate import run_calibration
from .config import load_config
from .runner import ScreenOnlySolver, SolverStop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-solver",
        description="Screen-only SOP automation for authorized practice questions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    calibrate = sub.add_parser("calibrate", help="Create config.yaml by mouse calibration")
    calibrate.add_argument("--config", default="config.yaml", help="Config path")

    run = sub.add_parser("run", help="Run the screen-only solver")
    run.add_argument("--config", default="config.yaml", help="Config path")
    run.add_argument("--once", action="store_true", help="Run one attempt only")
    run.add_argument("--dry-run", action="store_true", help="Do not click the screen")
    run.add_argument("--max-questions", type=int, help="Override max question count")

    inspect = sub.add_parser("inspect-config", help="Load and print normalized config")
    inspect.add_argument("--config", default="config.yaml", help="Config path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "calibrate":
            run_calibration(Path(args.config))
            return 0

        if args.command == "inspect-config":
            config = load_config(args.config)
            print(config.to_dict())
            return 0

        if args.command == "run":
            config = load_config(args.config).with_overrides(
                dry_run=True if args.dry_run else None,
                max_questions=args.max_questions,
            )
            solver = ScreenOnlySolver(config)
            solver.run(once=args.once)
            return 0
    except SolverStop as exc:
        print(f"[auto-solver] stopped: {exc}")
        return 2
    except KeyboardInterrupt:
        print("\n[auto-solver] interrupted")
        return 130
    except Exception as exc:
        print(f"[auto-solver] error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
