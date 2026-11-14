from pathlib import Path


def test_entrypoint_clears_stale_x_lock_before_starting_xvfb():
    script = (Path(__file__).parent / "bridge-entrypoint.sh").read_text()

    cleanup = script.index('rm -f "/tmp/.X${display_number}-lock"')
    launch = script.index('Xvfb "$DISPLAY"')

    assert cleanup < launch


def test_entrypoint_clears_stale_profile_singleton_locks_before_starting():
    script = (Path(__file__).parent / "bridge-entrypoint.sh").read_text()

    cleanup = script.index('rm -f "$profile_dir/SingletonLock"')
    launch = script.index("exec uvicorn")

    assert cleanup < launch
