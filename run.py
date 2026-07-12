import os
import subprocess
import sys

from app import create_app

app = create_app()


def _run_tests():
    """Run the pytest suite with coverage before launching the dev server.

    Runs in a subprocess so the tests' isolated config / temp database can't
    leak into the dev server's app instance. Test failures are reported but
    never block launch — the server always comes up. Set SKIP_TESTS=1 to skip
    the run entirely.
    """
    print('Running test suite with coverage before launch '
          '(set SKIP_TESTS=1 to skip)...')
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests',
             '--cov=app', '--cov-report=term', '--cov-report=html'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    except FileNotFoundError:
        # pytest isn't installed — carry on rather than blocking the server.
        print('pytest not found; skipping tests. '
              'Install dev deps with: pip install -r requirements-dev.txt')
        return

    if result.returncode == 0:
        print('All tests passed. Coverage HTML report: htmlcov/index.html')
    else:
        # Surface the failure but keep going — the app still launches.
        print(f'\nSome tests failed (pytest exit code {result.returncode}), '
              'but launching the app anyway. Coverage: htmlcov/index.html')


if __name__ == '__main__':
    # Only run tests on the initial launch, not on every Werkzeug reloader
    # restart (the reloader child sets WERKZEUG_RUN_MAIN).
    if os.environ.get('SKIP_TESTS') != '1' and not os.environ.get('WERKZEUG_RUN_MAIN'):
        _run_tests()
    app.run(debug=True)
