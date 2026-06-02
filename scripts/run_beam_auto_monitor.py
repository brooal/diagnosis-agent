from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.scheduler import BeamAutoDiagnosisScheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scheduler = BeamAutoDiagnosisScheduler(AutoDiagnosisConfig.from_env())
    scheduler.run_forever()


if __name__ == "__main__":
    main()
