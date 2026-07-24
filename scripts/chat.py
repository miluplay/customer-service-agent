"""v1.1 连续命令行聊天演示。"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.conversation_agent import run_conversation


def main() -> int:
    parser = argparse.ArgumentParser(description="Soundcore v1.1 多轮售后 Agent")
    parser.add_argument("--conversation-id", default="cli-demo", help="当前进程内的会话 ID")
    args = parser.parse_args()
    print("Soundcore v1.1 客服 Agent。输入 exit 结束会话。")
    while True:
        try:
            user_input = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if user_input.lower() in {"exit", "quit", "退出"}:
            return 0
        if not user_input:
            continue
        state = run_conversation(user_input, args.conversation_id)
        trace = state.get("tool_trace", [])
        for item in trace:
            print(f"[工具] {item['tool']} → {item.get('decision_code')} | 参数：{item.get('args')}")
        print(f"客服：{state['messages'][-1].content}")


if __name__ == "__main__":
    raise SystemExit(main())
