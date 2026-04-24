"""Parse Garak JSONL report and exit non-zero if critical vulnerabilities are found.

Usage: python3 redteam/parse_garak.py [--fail-on-critical] [--report-dir redteam]
"""
import argparse
import json
import sys
from pathlib import Path

CRITICAL_PROBE_CATEGORIES = {"promptinject", "leakage", "encoding"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse Garak vulnerability report")
    parser.add_argument("--fail-on-critical", action="store_true",
                        help="Exit 1 if any critical-category probes succeeded")
    parser.add_argument("--report-dir", default="redteam",
                        help="Directory to search for Garak JSONL reports")
    parser.add_argument("--max-allowed", type=int, default=0,
                        help="Maximum number of allowed failures before exit 1")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_files = sorted(report_dir.glob("*.jsonl"))

    if not report_files:
        print(f"No Garak report found in {report_dir}/ — skipping scan")
        return 0

    report_file = report_files[-1]
    print(f"Parsing Garak report: {report_file}")

    failures = []
    total = 0

    for line in report_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            total += 1
            if not r.get("passed", True):
                probe = r.get("probe", "unknown")
                failures.append({
                    "probe": probe,
                    "attempt": r.get("attempt_text", "")[:100],
                    "output": r.get("output_text", "")[:100],
                })
        except json.JSONDecodeError:
            continue

    print(f"\nGarak scan summary:")
    print(f"  Total probes run: {total}")
    print(f"  Vulnerabilities:  {len(failures)}")

    if failures:
        print("\nFailed probes:")
        for f in failures:
            print(f"  [{f['probe']}]")
            if f["attempt"]:
                print(f"    Attack: {f['attempt']}")

    critical_failures = [
        f for f in failures
        if any(cat in f["probe"] for cat in CRITICAL_PROBE_CATEGORIES)
    ]

    if args.fail_on_critical and critical_failures:
        print(f"\nERROR: {len(critical_failures)} critical vulnerability(s) found — blocking merge")
        return 1

    if len(failures) > args.max_allowed:
        print(f"\nERROR: {len(failures)} failures exceed max_allowed={args.max_allowed}")
        return 1

    print("\nGarak scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
