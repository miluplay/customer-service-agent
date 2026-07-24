"""Mock 订单与售后工具。

工具是业务事实的唯一裁决者：Agent 可以选择调用它们，但不能绕过资格检查
直接宣称订单已处理。
"""

from copy import deepcopy
from datetime import date, timedelta
from typing import Any


def _initial_orders(today: date | None = None) -> dict[str, dict[str, Any]]:
    """生成相对当前日期的演示订单，避免示例因时间流逝失效。"""
    today = today or date.today()
    return {
        "SC-1001": {"order_id": "SC-1001", "status_code": "processing", "status": "处理中", "can_cancel": True, "items": ["soundcore Liberty 4 NC"], "placed_at": str(today - timedelta(days=2)), "channel": "official", "order_type": "retail"},
        "SC-1002": {"order_id": "SC-1002", "status_code": "shipped", "status": "已发货", "can_cancel": False, "items": ["soundcore Space One"], "placed_at": str(today - timedelta(days=5)), "estimated_delivery": str(today + timedelta(days=2)), "channel": "official", "order_type": "retail"},
        "SC-1003": {"order_id": "SC-1003", "status_code": "delivered", "status": "已送达", "can_cancel": False, "items": ["soundcore Motion X600"], "placed_at": str(today - timedelta(days=6)), "delivered_at": str(today - timedelta(days=2)), "channel": "official", "order_type": "retail"},
        "SC-1004": {"order_id": "SC-1004", "status_code": "cancelled", "status": "已取消", "can_cancel": False, "items": ["soundcore AeroFit 2"], "placed_at": str(today - timedelta(days=4)), "channel": "official", "order_type": "retail"},
        "SC-1005": {"order_id": "SC-1005", "status_code": "delivered", "status": "已送达", "can_cancel": False, "items": ["soundcore Q45"], "placed_at": str(today - timedelta(days=20)), "delivered_at": str(today - timedelta(days=10)), "channel": "official", "order_type": "retail"},
        "SC-1006": {"order_id": "SC-1006", "status_code": "delivered", "status": "已送达", "can_cancel": False, "items": ["soundcore Motion 300"], "placed_at": str(today - timedelta(days=5)), "delivered_at": str(today - timedelta(days=2)), "channel": "official", "order_type": "business"},
        "SC-1007": {"order_id": "SC-1007", "status_code": "delivered", "status": "已送达", "can_cancel": False, "items": ["soundcore Liberty 4"], "placed_at": str(today - timedelta(days=5)), "delivered_at": str(today - timedelta(days=2)), "channel": "crowdfunding", "order_type": "retail"},
    }


_MOCK_ORDERS = _initial_orders()
_APPLICATION_SEQUENCE = 0


def get_order_status(order_id: str) -> dict[str, Any]:
    order = _MOCK_ORDERS.get(_normalize_order_id(order_id))
    if order is None:
        return _failure("get_order_status", order_id, "ORDER_NOT_FOUND", "未找到该订单，请确认订单号是否正确。")
    return _success("get_order_status", order, "ORDER_FOUND", "已找到订单。")


def cancel_order(order_id: str) -> dict[str, Any]:
    """取消尚未发货的订单；已发货订单改由拦截申请处理。"""
    order = _MOCK_ORDERS.get(_normalize_order_id(order_id))
    if order is None:
        return _failure("cancel_order", order_id, "ORDER_NOT_FOUND", "未找到该订单，请确认订单号是否正确。")
    if order["status_code"] == "cancelled":
        return _failure("cancel_order", order_id, "ORDER_ALREADY_CANCELLED", "该订单已经取消，无需重复操作。", order)
    if not order["can_cancel"]:
        return _failure("cancel_order", order_id, "CANCELLATION_NOT_ALLOWED", "订单已发货或送达，无法自动取消；请改走退货、退款或保修售后流程。", order)
    order.update({"status_code": "cancelled", "status": "已取消", "can_cancel": False})
    return _success("cancel_order", order, "ORDER_CANCELLED", "订单已成功取消。")


def check_return_eligibility(order_id: str, return_reason: str, issue_description: str | None = None, today: date | None = None) -> dict[str, Any]:
    """检查退货资格；结果可展示，但创建申请时还会再次检查。"""
    normalized = _normalize_order_id(order_id)
    order = _MOCK_ORDERS.get(normalized)
    checks: dict[str, Any] = {"order_found": bool(order)}
    if order is None:
        return _return_result(False, normalized, "RETURN_ORDER_NOT_FOUND", "未找到该订单，请确认订单号是否正确。", checks)
    checks["status"] = order["status_code"]
    if order["status_code"] == "cancelled":
        return _return_result(False, normalized, "RETURN_NOT_ELIGIBLE", "该订单已取消，无法重复创建售后申请。", checks, order)
    if order["status_code"] != "delivered":
        checks["delivered"] = False
        return _return_result(True, normalized, "PRE_DELIVERY_RETURN_ELIGIBLE", "订单尚未送达，可创建取消或物流拦截申请。", checks, order, "pre_delivery")
    checks["delivered"] = True
    if return_reason == "quality":
        checks["issue_description_provided"] = bool((issue_description or "").strip())
        if not checks["issue_description_provided"]:
            return _return_result(False, normalized, "RETURN_MANUAL_REVIEW_REQUIRED", "请描述产品质量问题后再创建售后申请。", checks, order)
        return _return_result(True, normalized, "QUALITY_RETURN_ELIGIBLE", "可创建质量问题售后申请，后续需补充材料并等待审核。", checks, order, "quality")
    reference = today or date.today()
    delivered_at = date.fromisoformat(order["delivered_at"])
    checks.update({"within_7_days": (reference - delivered_at).days <= 7, "official_retail": order["channel"] == "official" and order["order_type"] == "retail"})
    if not checks["within_7_days"]:
        return _return_result(False, normalized, "RETURN_WINDOW_EXPIRED", "该订单已超过送达后 7 天的无理由退货窗口，需要人工客服协助。", checks, order)
    if not checks["official_retail"]:
        return _return_result(False, normalized, "RETURN_NOT_ELIGIBLE", "该订单不属于官网零售订单，无法自动创建无理由退货申请。", checks, order)
    return _return_result(True, normalized, "RETURN_ELIGIBLE", "订单符合无理由退货资格。", checks, order, "non_quality")


def create_return_request(order_id: str, return_reason: str, issue_description: str | None = None) -> dict[str, Any]:
    """创建申请前始终重做资格检查，防止 LLM 跳过业务规则。"""
    eligibility = check_return_eligibility(order_id, return_reason, issue_description)
    if not eligibility["eligible"]:
        return {**eligibility, "action": "create_return_request", "ok": False}
    order = _MOCK_ORDERS[eligibility["order_id"]]
    if order.get("return_application"):
        return _return_result(False, eligibility["order_id"], "RETURN_ALREADY_CREATED", "该订单已创建售后申请，无需重复提交。", eligibility["checks"], order)
    global _APPLICATION_SEQUENCE
    _APPLICATION_SEQUENCE += 1
    application_id = f"RMA-{_APPLICATION_SEQUENCE:04d}"
    application_type = eligibility["application_type"]
    order["return_application"] = {"application_id": application_id, "type": application_type, "issue_description": issue_description}
    messages = {"pre_delivery": "已创建取消/物流拦截申请，将根据订单与物流状态处理。", "quality": "已创建质量问题售后申请，后续请按客服指引补充凭证或问题材料。", "non_quality": "已创建无理由退货申请，后续请按指引寄回商品及配件。"}
    return {"ok": True, "action": "create_return_request", "order_id": eligibility["order_id"], "decision_code": "RETURN_CREATED", "application_id": application_id, "application_type": application_type, "message": messages[application_type], "order": deepcopy(order), "eligibility": eligibility}


def handoff_to_human(reason: str = "需要进一步核实") -> dict[str, Any]:
    return {"ok": True, "action": "handoff_to_human", "decision_code": "HUMAN_HANDOFF", "message": f"{reason}，请通过声阔官方支持渠道联系人工客服，并准备订单号和产品信息。"}


def reset_mock_orders(today: date | None = None) -> None:
    global _MOCK_ORDERS, _APPLICATION_SEQUENCE
    _MOCK_ORDERS, _APPLICATION_SEQUENCE = _initial_orders(today), 0


def _success(action: str, order: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    return {"ok": True, "action": action, "order_id": order["order_id"], "decision_code": code, "message": message, "order": deepcopy(order)}


def _failure(action: str, order_id: str, code: str, message: str, order: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"ok": False, "action": action, "order_id": _normalize_order_id(order_id), "decision_code": code, "message": message}
    if order:
        result["order"] = deepcopy(order)
    return result


def _return_result(eligible: bool, order_id: str, code: str, message: str, checks: dict[str, Any], order: dict[str, Any] | None = None, application_type: str | None = None) -> dict[str, Any]:
    result = {"ok": eligible, "action": "check_return_eligibility", "order_id": order_id, "eligible": eligible, "decision_code": code, "message": message, "checks": checks, "next_action": "create_return_request" if eligible else "human_handoff"}
    if application_type:
        result["application_type"] = application_type
    if order:
        result["order"] = deepcopy(order)
    return result


def _normalize_order_id(order_id: str) -> str:
    return str(order_id).strip().upper()
