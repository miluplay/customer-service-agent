"""v1.1 分层多轮 Agent：Router → RAG Agent / 售后业务 Agent。"""

import json
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.graph.agent_tools import execute_tool, function_definitions, safe_tool_trace, tool_message_content
from src.guardrails.input_guardrail import validate_user_input
from src.guardrails.output_guardrail import validate_agent_output
from src.llm.deepseek import generate_tool_call_response, is_configured


class ConversationState(MessagesState):
    route: Literal["rag", "business", "blocked"]
    input_allowed: bool
    input_guardrail_reason: str | None
    output_allowed: bool
    output_guardrail_reason: str | None
    tool_trace: list[dict[str, Any]]


_ORDER_ID = re.compile(r"\bSC-\d{4}\b", re.IGNORECASE)
_POLICY_WORDS = ("政策", "保修", "质保", "多久", "产品信息", "参数", "怎么用")
_BUSINESS_WORDS = ("订单", "取消", "撤销", "退货", "退款", "物流", "到哪", "质量", "故障", "杂音", "坏", "不想要")
_QUALITY_WORDS = ("质量", "故障", "杂音", "坏", "损坏", "不能用", "问题")

ROUTER_PROMPT = """你是售后客服 Router。根据消息窗口选择：rag（产品、政策、保修知识问题）或 business（订单、取消、物流、退货、质量问题）。
只能调用 route_request 工具，不要回答用户。"""
RAG_PROMPT = """你是 soundcore 政策问答 Agent。必须先调用 search_policy，然后仅依据工具资料用简洁中文回答。若资料不足，建议人工客服。不要处理订单动作。"""
BUSINESS_PROMPT = """你是 soundcore 售后业务 Agent。根据完整对话处理订单状态、取消、退货和质量问题。
使用工具得到事实和执行结果，绝不自行声称申请、退款或取消成功。信息不足时直接用中文追问用户，不调用工具。
退货规则：未送达走取消/物流拦截申请；质量问题需要订单号和问题描述；无质量问题的已送达订单应先检查资格。创建申请工具会再次复核资格。"""


def _last_human(state: ConversationState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def check_input(state: ConversationState) -> dict:
    allowed, reason = validate_user_input(_last_human(state))
    if not allowed:
        return {"input_allowed": False, "input_guardrail_reason": reason, "route": "blocked", "messages": [AIMessage(content=reason or "该消息无法处理，请调整后再试。")]}
    return {"input_allowed": True, "input_guardrail_reason": None}


def route_after_input(state: ConversationState) -> str:
    return "router" if state.get("input_allowed") else "check_output"


def router(state: ConversationState) -> dict:
    route = _local_route(state)
    if is_configured():
        try:
            response = generate_tool_call_response(state["messages"], [_route_function()], ROUTER_PROMPT)
            if response.tool_calls and response.tool_calls[0]["name"] == "route_request":
                candidate = response.tool_calls[0]["args"].get("route")
                if candidate in {"rag", "business"}:
                    route = candidate
        except Exception:
            pass  # 无可用模型时使用确定性路由，保证演示可继续。
    return {"route": route}


def route_after_router(state: ConversationState) -> str:
    return "rag_agent" if state["route"] == "rag" else "business_agent"


def rag_agent(state: ConversationState) -> dict:
    message = _agent_response(state, {"search_policy"}, RAG_PROMPT, _rag_fallback)
    return {"messages": [message]}


def business_agent(state: ConversationState) -> dict:
    message = _agent_response(state, {"get_order_status", "cancel_order", "check_return_eligibility", "create_return_request", "handoff_to_human"}, BUSINESS_PROMPT, _business_fallback)
    return {"messages": [message]}


def route_after_agent(state: ConversationState) -> str:
    last = state["messages"][-1]
    return "execute_tools" if isinstance(last, AIMessage) and last.tool_calls else "check_output"


def execute_tools(state: ConversationState) -> dict:
    last = state["messages"][-1]
    messages, trace = [], list(state.get("tool_trace", []))
    for call in last.tool_calls:
        result = execute_tool(call["name"], call["args"])
        trace.append(safe_tool_trace(call["name"], call["args"], result))
        messages.append(ToolMessage(content=tool_message_content(result), tool_call_id=call["id"], name=call["name"]))
    return {"messages": messages, "tool_trace": trace}


def route_after_tools(state: ConversationState) -> str:
    return "rag_agent" if state["route"] == "rag" else "business_agent"


def check_output(state: ConversationState) -> dict:
    answer = str(state["messages"][-1].content)
    allowed, reason = validate_agent_output(answer)
    if allowed:
        allowed, reason = _validate_claims_against_tools(answer, state)
    if allowed:
        return {"output_allowed": True, "output_guardrail_reason": None}
    return {"output_allowed": False, "output_guardrail_reason": reason, "messages": [AIMessage(content="为确保您的信息安全和售后权益，此问题暂时无法自动回复。请联系人工客服进一步处理。")]}


def _validate_claims_against_tools(answer: str, state: ConversationState) -> tuple[bool, str | None]:
    """阻止模型在没有对应工具结果时声称业务动作已完成。"""
    codes = {item.get("decision_code") for item in state.get("tool_trace", [])}
    if ("申请已创建" in answer or "已创建退货" in answer) and "RETURN_CREATED" not in codes:
        return False, "回复声称申请已创建，但当前会话没有对应工具结果。"
    if "订单已成功取消" in answer and "ORDER_CANCELLED" not in codes:
        return False, "回复声称订单已取消，但当前会话没有对应工具结果。"
    return True, None


def _agent_response(state: ConversationState, tools: set[str], prompt: str, fallback) -> AIMessage:
    if is_configured():
        try:
            return generate_tool_call_response(state["messages"], function_definitions(tools), prompt)
        except Exception:
            # 仅降级为追问或本地 Mock 工具；真实业务仍由工具做最终裁决。
            pass
    return fallback(state)


def _local_route(state: ConversationState) -> Literal["rag", "business"]:
    latest = _last_human(state).lower()
    history = " ".join(str(m.content).lower() for m in state["messages"] if isinstance(m, HumanMessage))
    # 最新一轮表达完整的新知识问题时，应覆盖先前的订单上下文；仅订单号等
    # 省略回答才依赖历史来续接业务流程。
    if any(word in latest for word in _POLICY_WORDS) and not any(word in latest for word in _BUSINESS_WORDS):
        return "rag"
    if _ORDER_ID.search(latest) or any(word in latest for word in _BUSINESS_WORDS):
        return "business"
    return "business" if any(word in history for word in _BUSINESS_WORDS) else "rag"


def _rag_fallback(state: ConversationState) -> AIMessage:
    if any(isinstance(m, ToolMessage) and m.name == "search_policy" for m in state["messages"]):
        result = _last_tool_result(state)
        if result.get("results"):
            source = result["results"][0]["metadata"].get("source", "政策资料")
            return AIMessage(content=f"根据《{source.split('/')[-1]}》：\n{result['results'][0]['text'].strip()}")
        return AIMessage(content="暂时没有找到足够的政策资料，请联系人工客服确认。")
    return AIMessage(content="", tool_calls=[_call("search_policy", {"query": _last_human(state)})])


def _business_fallback(state: ConversationState) -> AIMessage:
    latest = _last_human(state)
    history = " ".join(str(m.content) for m in state["messages"] if isinstance(m, HumanMessage))
    result = _last_tool_result(state)
    if result:
        if result.get("action") == "check_return_eligibility" and result.get("eligible"):
            reason = "quality" if result.get("application_type") == "quality" else "non_quality"
            description = latest if reason == "quality" else None
            return AIMessage(content="", tool_calls=[_call("create_return_request", {"order_id": result["order_id"], "return_reason": reason, "issue_description": description})])
        return AIMessage(content=result.get("message", "已完成处理。"))
    order_id = _extract_order_id(history)
    if not order_id:
        return AIMessage(content="为了继续处理，请提供订单号，例如 SC-1003。")
    if any(word in history for word in ("取消", "撤销")) and "退货" not in history:
        return AIMessage(content="", tool_calls=[_call("cancel_order", {"order_id": order_id})])
    if any(word in history for word in ("状态", "物流", "到哪", "进度", "什么时候到", "查询")) and "退" not in history:
        return AIMessage(content="", tool_calls=[_call("get_order_status", {"order_id": order_id})])
    quality = any(word in history for word in _QUALITY_WORDS)
    if quality and len(latest.replace(order_id, "").strip()) < 3:
        return AIMessage(content="请简要描述产品遇到的质量问题，例如杂音、无法开机或无法充电。")
    return AIMessage(content="", tool_calls=[_call("check_return_eligibility", {"order_id": order_id, "return_reason": "quality" if quality else "non_quality", "issue_description": latest if quality else None})])


def _last_tool_result(state: ConversationState) -> dict:
    for message in reversed(state["messages"]):
        if isinstance(message, ToolMessage):
            try:
                return json.loads(str(message.content))
            except json.JSONDecodeError:
                return {}
    return {}


def _extract_order_id(text: str) -> str | None:
    match = _ORDER_ID.search(text)
    return match.group(0).upper() if match else None


def _call(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"local-{name}", "type": "tool_call"}


def _route_function() -> dict:
    return {"type": "function", "function": {"name": "route_request", "description": "选择后续专用 Agent。", "parameters": {"type": "object", "properties": {"route": {"type": "string", "enum": ["rag", "business"]}}, "required": ["route"], "additionalProperties": False}}}


_CHECKPOINTER = MemorySaver()


def build_conversation_graph():
    workflow = StateGraph(ConversationState)
    for name, node in (("check_input", check_input), ("router", router), ("rag_agent", rag_agent), ("business_agent", business_agent), ("execute_tools", execute_tools), ("check_output", check_output)):
        workflow.add_node(name, node)
    workflow.add_edge(START, "check_input")
    workflow.add_conditional_edges("check_input", route_after_input, {"router": "router", "check_output": "check_output"})
    workflow.add_conditional_edges("router", route_after_router, {"rag_agent": "rag_agent", "business_agent": "business_agent"})
    workflow.add_conditional_edges("rag_agent", route_after_agent, {"execute_tools": "execute_tools", "check_output": "check_output"})
    workflow.add_conditional_edges("business_agent", route_after_agent, {"execute_tools": "execute_tools", "check_output": "check_output"})
    workflow.add_conditional_edges("execute_tools", route_after_tools, {"rag_agent": "rag_agent", "business_agent": "business_agent"})
    workflow.add_edge("check_output", END)
    return workflow.compile(checkpointer=_CHECKPOINTER)


def run_conversation(user_input: str, conversation_id: str = "default") -> ConversationState:
    graph = build_conversation_graph()
    return graph.invoke({"messages": [HumanMessage(content=user_input)], "tool_trace": []}, config={"configurable": {"thread_id": conversation_id}})
