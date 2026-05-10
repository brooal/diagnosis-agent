# scripts/test_power_faults.py

from app.data_sources.remote_db import RemoteDB
from app.data_sources.pv_repository import PVRepository
from app.tools.diagnosis_tools import DiagnosisTools


def main():
    db = RemoteDB()
    repo = PVRepository(db)
    tools = DiagnosisTools(repo)

    result = tools.diagnose_power_faults(
        fault_time="2026-05-06 10:02:31",
        window_seconds=10,
    )

    print("ok:", result.ok)
    print("summary:", result.summary)
    print(result.output)


if __name__ == "__main__":
    main()