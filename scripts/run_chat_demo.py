
from app.agent.runner import DiagnosisAgentRunner

def main():
    runner = DiagnosisAgentRunner()

    state = runner.run_chat(
        user_query="帮我分析一下今天10：00到10：05是否发生了束流掉束，并检查四级铁电源有没有异常",
        time_window={
            "start": "2026-05-06T10:00:00+09:00",
            "end": "2026-05-06T10:00:00+09:00",
        },
        scope={
            "beam_current_pv" : "RNG:BEAM:CURRENT",
            "quadruple_pattern" : "Q*:PS:*",
        },
    )
    print(state['final_answer'])
    print("trace_id",state['trace_id'])

if __name__ == "__main__":
    main()
