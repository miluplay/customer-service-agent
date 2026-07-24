"""验证 Function Calling 工具白名单、参数校验与动作前资格复核。"""

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.agent_tools import execute_tool
from src.graph.conversation_agent import _validate_claims_against_tools
from src.tools.order_tools import reset_mock_orders


def main() -> int:
    reset_mock_orders(date.today())
    cases = [
        ("unknown", execute_tool("delete_orders", {}), "UNKNOWN_TOOL"),
        ("invalid", execute_tool("get_order_status", {"order_id": "not-an-order"}), "INVALID_TOOL_ARGUMENTS"),
        ("quality-missing-description", execute_tool("create_return_request", {"order_id": "SC-1003", "return_reason": "quality"}), "RETURN_MANUAL_REVIEW_REQUIRED"),
        ("expired-recheck", execute_tool("create_return_request", {"order_id": "SC-1005", "return_reason": "non_quality"}), "RETURN_WINDOW_EXPIRED"),
    ]
    passed = 0
    for name, result, expected in cases:
        ok = result.get("decision_code") == expected
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
        passed += ok
    claim_ok, _ = _validate_claims_against_tools("已创建退货申请", {"tool_trace": []})
    claim_blocked = not claim_ok
    print(f"unverified-claim: {'PASS' if claim_blocked else 'FAIL'}")
    passed += claim_blocked
    total = len(cases) + 1
    print(f"Passed: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
