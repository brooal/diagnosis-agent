from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes import _primary_cause_from_report_text


def test_primary_cause_from_report_text_extracts_pv_and_meaning() -> None:
    text = (
        "主要候选原因：速调管调制器故障：报警信号 "
        "`RNG:TOPOFF:KLY:Err:mbbo` 在事件时刻值为 3，含义为 `KLY3_Err`。"
    )

    cause = _primary_cause_from_report_text(text)

    assert cause["pv"] == "RNG:TOPOFF:KLY:Err:mbbo"
    assert cause["meaning"] == "KLY3_Err"
    assert cause["source"] == "report_text"
