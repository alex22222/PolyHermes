from pathlib import Path


def test_entrypoint_clears_stale_x_lock_before_starting_xvfb():
    script = (Path(__file__).parent / "bridge-entrypoint.sh").read_text()

    cleanup = script.index('rm -f "/tmp/.X${display_number}-lock"')
    launch = script.index('Xvfb "$DISPLAY"')

    assert cleanup < launch
