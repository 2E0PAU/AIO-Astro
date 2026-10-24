import os
import subprocess
import sys
from pathlib import Path


def test_desktop_workflow_in_separate_qt_process(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("desktop_smoke.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "shutdown passed" in result.stdout


def test_mount_and_chart_workflow_in_separate_qt_process(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("mount_desktop_smoke.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "profiles passed" in result.stdout


def test_imaging_controls_with_alpaca_peer_in_separate_qt_process(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("imaging_desktop_smoke.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "recovery passed" in result.stdout


def test_colour_capture_preview_and_fits_in_separate_qt_process(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("colour_desktop_smoke.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ordering passed" in result.stdout
