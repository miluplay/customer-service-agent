"""Function Calling 工具 schema、执行器与安全校验。"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from src.rag.retriever import search_default
from src.tools.order_tools import (
    cancel_order,
    check_return_eligibility,
    create_return_request,
    get_order_status,
    handoff_to_human,
)


class OrderIdArgs(BaseModel):
    order_id: str = Field(pattern=r"(?i)^SC-\d{4}$")


class ReturnCheckArgs(OrderIdArgs):
    return_reason: Literal["quality", "non_quality"]
    issue_description: str | None = Field(default=None, max_length=500)


class HandoffArgs(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class PolicyArgs(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


TOOL_MODELS = {
    "search_policy": PolicyArgs,
    "get_order_status": OrderIdArgs,
    "cancel_order": OrderIdArgs,
    "check_return_eligibility": ReturnCheckArgs,
    "create_return_request": ReturnCheckArgs,
    "handoff_to_human": HandoffArgs,
}


def function_definitions(names: set[str]) -> list[dict[str, Any]]:
    """生成 OpenAI/DeepSeek 兼容 Function Calling schema。"""
    descriptions = {
        "search_policy": "检索声阔政策与产品知识；只能依据结果回答。",
        "get_order_status": "查询指定订单的真实 Mock 状态。",
        "cancel_order": "取消尚未发货的订单。",
        "check_return_eligibility": "检查退货资格；不创建申请。",
        "create_return_request": "创建申请，但会再次校验资格，不能跳过检查。",
        "handoff_to_human": "创建人工协助结果，用于无法自动处理的情况。",
    }
    return [{"type": "function", "function": {"name": name, "description": descriptions[name], "parameters": TOOL_MODELS[name].model_json_schema()}} for name in sorted(names)]


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """白名单与 Pydantic 校验后的唯一执行入口。"""
    model = TOOL_MODELS.get(name)
    if model is None:
        return {"ok": False, "decision_code": "UNKNOWN_TOOL", "message": "该工具不在允许的工具白名单中。"}
    try:
        values = model.model_validate(args).model_dump()
    except ValidationError as error:
        return {"ok": False, "decision_code": "INVALID_TOOL_ARGUMENTS", "message": "工具参数不符合要求。", "errors": error.errors(include_url=False)}
    if name == "search_policy":
        results = search_default(values["query"])
        return {"ok": bool(results), "action": name, "decision_code": "POLICY_FOUND" if results else "POLICY_NOT_FOUND", "results": results}
    if name == "get_order_status":
        return get_order_status(**values)
    if name == "cancel_order":
        return cancel_order(**values)
    if name == "check_return_eligibility":
        return check_return_eligibility(**values)
    if name == "create_return_request":
        return create_return_request(**values)
    return handoff_to_human(**values)


def tool_message_content(result: dict[str, Any]) -> str:
    """给模型的工具结果保持结构化；CLI 仅展示其摘要。"""
    return json.dumps(result, ensure_ascii=False, default=str)


def safe_tool_trace(name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    redacted_args = {key: ("[已提供]" if key == "issue_description" else value) for key, value in args.items()}
    return {"tool": name, "args": redacted_args, "decision_code": result.get("decision_code"), "ok": result.get("ok")}
