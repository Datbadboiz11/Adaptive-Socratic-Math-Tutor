"""Run every retained test; retired source bundles have no test exclusions."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junitxml', default='artifacts/current-release-tests.xml')
    parser.add_argument('--maxfail', type=int, default=0)
    parser.add_argument('--collect-only', action='store_true')
    args = parser.parse_args()
    command = [sys.executable, '-m', 'pytest', 'tests', '-q', '--disable-warnings',
               '-o', 'cache_dir=artifacts/release-pytest-cache', '--junitxml=' + args.junitxml]
    if args.maxfail:
        command += ['--maxfail=' + str(args.maxfail)]
    if args.collect_only:
        command += ['--collect-only']
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
