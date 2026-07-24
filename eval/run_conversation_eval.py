"""验证 v1.1 多轮 Agent 的关键闭环。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.conversation_agent import run_conversation
from src.tools.order_tools import reset_mock_orders


def _run_case(case_id: str, turns: list[str], expected_code: str, expected_text: str) -> bool:
    reset_mock_orders()
    state = {}
    for turn in turns:
        state = run_conversation(turn, case_id)
    answer = str(state["messages"][-1].content)
    codes = [item.get("decision_code") for item in state.get("tool_trace", [])]
    ok = expected_code in codes and expected_text in answer
    print(f"{case_id}: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"  codes={codes}; answer={answer}")
    return ok


def main() -> int:
    cases = [
        ("quality", ["我要退货", "SC-1003，耳机有杂音"], "RETURN_CREATED", "质量问题售后申请"),
        ("normal", ["我要退货", "SC-1003"], "RETURN_CREATED", "无理由退货申请"),
        ("intercept", ["订单 SC-1002 我不想要了，想退货"], "RETURN_CREATED", "取消/物流拦截申请"),
        ("expired", ["我要退货 SC-1005"], "RETURN_WINDOW_EXPIRED", "超过送达后 7 天"),
        ("business", ["我要退货 SC-1006"], "RETURN_NOT_ELIGIBLE", "不属于官网零售订单"),
        ("status", ["查询订单 SC-1002 的物流"], "ORDER_FOUND", "已找到订单"),
    ]
    passed = sum(_run_case(*case) for case in cases)
    print(f"Passed: {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
