"""대화형 CLI 인터페이스.

사용법:
    python scripts/chat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.workflow import app


def main():
    print("=" * 50)
    print("  면접위키 멀티에이전트 챗봇")
    print("  종료: quit / exit / q")
    print("=" * 50)
    print()

    while True:
        try:
            query = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("종료합니다.")
            break

        print()

        try:
            result = app.invoke({
                "query": query,
                "messages": [],
                "agent_type": "",
                "complexity": "",
                "response": "",
            })

            print()
            print("-" * 50)
            print(result["response"])
            print("-" * 50)

        except Exception as e:
            print(f"오류 발생: {e}")

        print()


if __name__ == "__main__":
    main()