from app.agent.runner import DiagnosisAgentRunner

from app.db.session import SessionLocal

def main():
    db = SessionLocal()

    try:
        runner = DiagnosisAgentRunner(db)
        state = runner.run_chat(
            user_query="帮我分析 10:00 到 10:05 是否发生了束流掉束，并检查四级铁电源有没有异常",
            time_window={
                "start": "2026-05-06T10:00:00+09:00",
                "end": "2026-05-06T10:05:00+09:00",
            },
            scope={
                "beam_current_pv": "RING:BEAM:CURRENT",
                "quadrupole_pattern": "Q*:PS:*",
            },
        )
        print("case_uid" , state["case_uid"])
        print("run_uid" , state["run_uid"])
        print()
        print(state['final_answer'])
    finally:
        db.close()

if __name__ == "__main__":
    main()

