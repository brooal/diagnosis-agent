from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.manual_diagnosis import BeamManualDiagnosisRunner
from app.tools import build_tool_registry
from app.tools.base import get_tool_runtime
from app.utils.json import make_json_safe


def main() -> None:
    parser = argparse.ArgumentParser(description="Run user-triggered beam diagnosis for a time range.")
    parser.add_argument("--start", required=True, help="Start time, e.g. 2026-05-24T22:00:00+08:00")
    parser.add_argument("--end", required=True, help="End time, e.g. 2026-05-24T23:00:00+08:00")
    args = parser.parse_args()

    build_tool_registry()
    repo = get_tool_runtime().pv_repo
    if repo is None:
        raise RuntimeError("PV repository is not initialized.")

    result = BeamManualDiagnosisRunner(
        repo=repo,
        config=AutoDiagnosisConfig.from_env(),
    ).run(
        start=args.start,
        end=args.end,
    )
    print(json.dumps(make_json_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
