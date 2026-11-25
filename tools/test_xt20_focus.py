"""xt20_focus against a fake gphoto2 whose lens lands one count short on the first move.

FAKE_FAIL lists failures for the first gphoto2 calls, one per call (busy, lost, claimed), using
libgphoto2's real wording, so the busy retry, session reopen and give-up paths run without a camera.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name('xt20_focus.py')
FAKE = r'''#!/usr/bin/env bash
st="$FAKE_STATE"; [ -f "$st" ] || echo 495 > "$st"
args=("$@"); [ "${args[0]}" = "--port" ] && args=("${args[@]:2}")
echo "${args[*]}" >> "$st.log"
k="$st.k"; i=$(cat "$k" 2>/dev/null || echo 0); echo $((i+1)) > "$k"
read -ra fails <<< "${FAKE_FAIL:-}"
case "${fails[$i]:-}" in
  busy) printf '\n*** Error ***              \nPTP Device Busy\n*** Error (-110: \x27I/O in progress\x27) ***\n' >&2; exit 1 ;;
  lost) printf '\n*** Error ***              \nPTP I/O Error\n*** Error (-7: \x27I/O problem\x27) ***\n' >&2; exit 1 ;;
  claimed) printf '\n*** Error (-53: \x27Could not claim the USB device\x27) ***\n' >&2; exit 1 ;;
esac
case "${args[0]}" in
  --get-config)
    if [ "${args[1]}" = manualfocusdrive ]; then printf 'Label: Drive Fuji Manual focus\nReadonly: 0\nType: RADIO\nCurrent: %s\nChoice: 0 0\nEND\n' "$(cat "$st")"
    else echo "*** Error: ${args[1]} not found" >&2; exit 1; fi ;;
  --set-config-value)
    v=${args[1]#manualfocusdrive=}; n="$st.n"; c=$(cat "$n" 2>/dev/null || echo 0); echo $((c+1)) > "$n"
    if [ "$c" = 0 ]; then echo $((v-1)) > "$st"; else echo "$v" > "$st"; fi ;;
  --set-config) echo "must not use --set-config" >&2; exit 9 ;;
esac
'''


@pytest.fixture
def focus(tmp_path):
    fake = tmp_path / 'gphoto2'
    fake.write_text(FAKE)
    fake.chmod(0o755)
    env = dict(os.environ, GPHOTO2=str(fake), FAKE_STATE=str(tmp_path / 'state'), XT20_FOCUS_DB=str(tmp_path / 'db.json'),
               XT20_FOCUS_BACKOFF='0.01')

    def run(*args, check=True, fail=''):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=dict(env, FAKE_FAIL=fail),
                                capture_output=True, text=True)
        assert not check or result.returncode == 0, result.stderr
        return result
    return run


def test_save_goto_and_retry(focus):
    assert focus('get').stdout.strip() == '495'
    assert 'saved stars = 495' in focus('save', 'stars').stdout
    moved = focus('--wait', '1', 'set', '117').stdout
    assert 'move 2' in moved and 'OK: position 117' in moved
    assert 'OK: position 495' in focus('--wait', '1', 'goto', 'stars').stdout
    assert 'OK: position 492' in focus('--wait', '1', 'nudge', '-3').stdout
    assert focus('list').stdout.split()[:2] == ['stars', '495']
    assert focus('goto', 'nope', check=False).returncode != 0
    assert 'removed' in focus('rm', 'stars').stdout


def test_small_values_are_sent_as_values_not_choice_indexes(focus):
    assert 'OK: position 3' in focus('--wait', '1', 'set', '3').stdout


def test_busy_is_retried_with_backoff(focus, tmp_path):
    result = focus('get', fail='busy busy')
    assert result.stdout.strip() == '495'
    assert result.stderr.count('camera busy') == 2
    assert (tmp_path / 'state.log').read_text().splitlines() == ['--get-config manualfocusdrive'] * 3


def test_busy_during_a_move_still_reads_back(focus):
    # get (busy, then ok), set (busy, then ok, lands 1 short), read back, correction, read back
    moved = focus('--wait', '1', 'set', '117', fail='busy ok busy').stdout
    assert 'move 1: read back 116 (error -1), mismatch' in moved
    assert 'move 2: read back 117 (error +0)' in moved and 'OK: position 117' in moved


def test_lost_reply_reopens_the_session_once(focus, tmp_path):
    result = focus('get', fail='lost')
    assert result.stdout.strip() == '495' and 'reopening the session' in result.stderr
    (tmp_path / 'state.k').unlink()  # restart the fake's per-call failure script
    result = focus('get', fail='lost lost', check=False)
    assert result.returncode != 0 and 'stopped answering' in result.stderr


def test_busy_gives_up_after_the_retry_budget(focus):
    result = focus('get', fail=' '.join(['busy'] * 6), check=False)
    assert result.returncode != 0 and result.stderr.count('camera busy') == 5
    assert 'stayed busy' in result.stderr


def test_claimed_camera_is_not_retried(focus, tmp_path):
    result = focus('get', fail='claimed', check=False)
    assert result.returncode != 0 and 'Another program holds the camera' in result.stderr
    assert len((tmp_path / 'state.log').read_text().splitlines()) == 1


def test_mismatch_is_reported_when_the_lens_never_lands(focus, tmp_path):
    (tmp_path / 'state.n').write_text('0')
    result = focus('--wait', '1', '--retries', '0', 'set', '200', check=False)
    assert result.returncode == 2
    assert 'mismatch' in result.stdout and 'NOT REACHED: position 199, target 200' in result.stdout
