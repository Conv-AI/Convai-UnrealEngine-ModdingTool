"""Run every tests/test_*.py in one process: `python tests/selfcheck.py`. No network needed."""
import glob
import logging
import os
import runpy
import sys
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_LOGGER = logging.getLogger('ConvaiTool')


def main() -> int:
    failed = []
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, 'test_*.py'))):
        name = os.path.basename(path)
        # Checks silence the tool logger to keep their own output clean, and one of
        # them asserts on what it logs. In one process that has to be undone.
        disabled, handlers = TOOL_LOGGER.disabled, list(TOOL_LOGGER.handlers)
        try:
            runpy.run_path(path, run_name='__main__')
        except SystemExit as exit_call:
            # A check with nothing to run (no display) exits 0 rather than failing.
            if exit_call.code:
                failed.append(name)
                print(f'{name}: FAIL (exit {exit_call.code})')
                continue
        except Exception:
            failed.append(name)
            print(f'{name}: FAIL')
            traceback.print_exc()
            continue
        finally:
            TOOL_LOGGER.disabled = disabled
            TOOL_LOGGER.handlers[:] = handlers
        print(f'{name}: OK')

    print(f'\n{"FAILED: " + ", ".join(failed) if failed else "all checks passed"}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
