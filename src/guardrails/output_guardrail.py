"""输出端防护：阻止敏感信息泄露、无依据承诺和明显编造的售后政策。"""

import re


_PAYMENT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
_UNSUPPORTED_PROMISE_PATTERN = re.compile(
    r"(?:保证|承诺|一定|肯定).{0,24}(?:退款|退款到账|退货|补偿|送达)",
)
_UNSUPPORTED_POLICY_PATTERN = re.compile(r"终身保修|永久保修|无条件退款")


def validate_agent_output(output: str) -> tuple[bool, str | None]:
    """检查 Agent 回复能否安全地发送给用户。"""
    text = str(output or "").strip()

    if not text:
        return False, "Agent 未生成有效回复。"

    if _PAYMENT_CARD_PATTERN.search(text):
        return False, "回复包含疑似支付卡信息，不能发送。"

    if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
        return False, "回复包含疑似访问凭证，不能发送。"

    if _UNSUPPORTED_PROMISE_PATTERN.search(text):
        return False, "回复包含未经确认的售后承诺，不能发送。"

    if _UNSUPPORTED_POLICY_PATTERN.search(text):
        return False, "回复包含未在当前政策中确认的售后条款，不能发送。"

    return True, None
