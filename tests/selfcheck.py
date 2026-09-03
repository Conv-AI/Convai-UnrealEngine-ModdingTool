"""Run every tests/test_*.py: `python tests/selfcheck.py`. No network needed.

Each check runs in its own interpreter. They are documented to be runnable one at a
time, and several of them seed process-wide state -- the remote config, the tool
logger's handlers -- which in one shared process makes the result depend on the order
the files happen to sort in.
"""
import glob
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    failed = []
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, 'test_*.py'))):
        name = os.path.basename(path)
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, path], capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                env=environment)
        if result.returncode:
            failed.append(name)
            print(f'{name}: FAIL (exit {result.returncode})')
            print((result.stdout or '').rstrip())
            print((result.stderr or '').rstrip())
            continue

        # A check with nothing to run - no display - prints its own reason and passes.
        last = (result.stdout or '').strip().splitlines()
        print(f'{name}: OK{"" if not last else " (" + last[-1] + ")"}')

    print(f'\n{"FAILED: " + ", ".join(failed) if failed else "all checks passed"}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
