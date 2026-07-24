"""输入端防护：拦截空消息、过长内容和不应发送给客服的敏感信息。"""

import re

from src.config import settings


_PAYMENT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def validate_user_input(user_input: str) -> tuple[bool, str | None]:
    """检查用户消息是否可安全进入后续 Agent 流程。"""
    text = str(user_input or "").strip()

    if not text:
        return False, "请输入您需要咨询的售后问题。"

    if len(text) > settings.max_input_length:
        return False, f"消息过长，请将内容控制在 {settings.max_input_length} 个字符以内。"

    if _PAYMENT_CARD_PATTERN.search(text):
        return False, "为保护您的支付安全，请不要发送完整银行卡号或支付卡信息。"

    if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
        return False, "为保护您的账户安全，请不要发送 API 密钥或访问凭证。"

    return True, None
