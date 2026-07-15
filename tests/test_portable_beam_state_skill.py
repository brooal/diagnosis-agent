from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "app" / "portable_skills" / "beam-state-diagnosis"
SCRIPT_PATH = SKILL_DIR / "scripts" / "diagnose.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("portable_beam_state_diagnosis", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_portable_beam_state_detects_beam_trip() -> None:
    module = _load_module()

    result = module.diagnose(
        {
            "start": "2026-05-06T10:00:00+08:00",
            "end": "2026-05-06T10:05:00+08:00",
            "beam_channel": "RNG:BEAM:CURR",
            "beam_samples": [
                {"time": "2026-05-06T10:00:00+08:00", "value": 500.0},
                {"time": "2026-05-06T10:02:31+08:00", "value": 20.0},
            ],
        }
    )

    assert result["ok"]
    assert result["output"]["phenomena"][0]["type"] == "beam_trip"
    assert result["candidate_causes"][0]["cause_type"] == "beam_trip"
    assert result["output"]["recommended_next_skills"][0]["name"] == "quadrupole_power_diagnosis"


def test_portable_beam_state_detects_topoff_decay() -> None:
    module = _load_module()

    result = module.diagnose(
        {
            "start": "2026-05-13T12:00:00+08:00",
            "end": "2026-05-13T12:02:00+08:00",
            "beam_channel": "RNG:BEAM:CURR",
            "beam_samples": [
                {"time": "2026-05-13T11:56:00+08:00", "value": 500.0},
                {"time": "2026-05-13T12:00:00+08:00", "value": 480.0},
            ],
            "mode_samples": [
                {"time": "2026-05-13T11:56:17+08:00", "value": 0, "channel_id": 2418},
                {"time": "2026-05-13T12:01:00+08:00", "value": 1, "channel_id": 2418},
            ],
            "alarm_samples": [
                {
                    "time": "2026-05-13T11:56:17+08:00",
                    "value": 3,
                    "pv": "RNG:TOPOFF:KLY:Err:mbbo",
                    "channel_id": 2427,
                    "subsystem": "KLY",
                    "meaning": "KLY3_Err",
                    "description": "KLY 调制器故障报警",
                }
            ],
        }
    )

    assert result["ok"]
    assert result["output"]["phenomena"][0]["classification"] == "topoff_decay"
    assert result["candidate_causes"][0]["meaning"] == "KLY3_Err"
    assert result["output"]["recommended_next_skills"][0]["name"] == "decay_cause_analysis"


def test_portable_beam_state_script_cli_roundtrip(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(
        json.dumps(
            {
                "start": "2026-05-06T10:00:00+08:00",
                "end": "2026-05-06T10:05:00+08:00",
                "beam_samples": [
                    {"time": "2026-05-06T10:00:00+08:00", "value": 500.0},
                    {"time": "2026-05-06T10:01:00+08:00", "value": 501.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--input", str(input_path), "--output", str(output_path)],
        check=True,
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"]
    assert result["output"]["phenomena"][0]["type"] == "normal"
