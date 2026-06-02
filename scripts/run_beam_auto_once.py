from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auto_diagnosis.beam_monitor import BeamAutoMonitor
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.utils.json import make_json_safe


def main() -> None:
    init_db()
    config = AutoDiagnosisConfig.from_env()
    db = SessionLocal()
    try:
        result = BeamAutoMonitor(db=db, config=config).run_once()
        print(json.dumps(make_json_safe(result), ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
