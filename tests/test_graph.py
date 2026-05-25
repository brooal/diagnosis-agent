from app.agent.nodes import route_after_act, route_after_plan


def test_route_after_plan_goes_to_fail_when_state_failed() -> None:
    assert route_after_plan({"status": "failed"}) == "fail"


def test_route_after_act_continues_until_max_steps() -> None:
    assert route_after_act({"status": "running", "step": 1, "max_steps": 3}) == "plan"
    assert route_after_act({"status": "running", "step": 3, "max_steps": 3}) == "summarize"
