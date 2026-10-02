"""Run the engine's script-based tests in isolated Python processes."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parent
DATABASE_TESTS = {"test_market_repository.py", "test_zone_boundary_service.py",
                  "test_engine_results_repository_mongodb.py"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-database", action="store_true",
                        help="Also run tests that require a live MongoDB connection")
    parser.add_argument("--verbose", action="store_true", help="Show output from successful tests")
    args = parser.parse_args()
    discovered = sorted(SCRIPTS.glob("test_*.py"))
    selected = [path for path in discovered
                if args.include_database or path.name not in DATABASE_TESTS]
    if not selected:
        print("ERROR: No test scripts found.", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    # Legacy script tests use assert; inherited optimization must not disable it.
    environment.pop("PYTHONOPTIMIZE", None)
    failed = []
    for path in selected:
        try:
            result = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(path)],
                cwd=SCRIPTS.parent, env=environment, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=30,
            )
        except subprocess.TimeoutExpired:
            failed.append(path.name)
            print(f"FAIL {path.name}: exceeded 30 seconds")
            continue
        except OSError as error:
            failed.append(path.name)
            print(f"FAIL {path.name}: {error}")
            continue
        successful = result.returncode == 0
        print(f"{'PASS' if successful else 'FAIL'} {path.name}")
        if not successful:
            failed.append(path.name)
        if args.verbose or not successful:
            output = result.stdout + result.stderr
            if output:
                print(output.rstrip())

    skipped = len(discovered) - len(selected)
    print(f"\nTest scripts: {len(selected) - len(failed)} passed, "
          f"{len(failed)} failed, {skipped} skipped.")
    if skipped:
        print("MongoDB integration tests skipped; use --include-database to enable them.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
