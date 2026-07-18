import argparse
import json

try:
    from .qa import QAResponder, QAConfig
except ImportError:
    from qa import QAResponder, QAConfig


def _load_parsed(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # 兼容两类输入：
    # 1) parser.py 直接输出（含 parsed_pages）
    # 2) generate.py 输出（在 parsed 字段内）
    if "parsed_pages" in data:
        return data
    if "parsed" in data and "parsed_pages" in data["parsed"]:
        return data["parsed"]
    raise ValueError("输入 JSON 不包含 parsed_pages，无法执行问答")


def main() -> None:
    cli = argparse.ArgumentParser(description="问答溯源与重讲测试入口")
    cli.add_argument("parsed_json", help="解析结果 JSON 路径")
    cli.add_argument("question", help="学生问题")
    cli.add_argument("--page", type=int, default=1, help="当前页码")
    cli.add_argument("--mode", default="llm", choices=["mock", "llm"], help="响应模式")
    cli.add_argument("--model", default=os.getenv("AI_MODEL", "qwen-turbo"), help="LLM 模型名（mode=llm 时生效）")
    cli.add_argument("--out", default=None, help="可选：输出结果 JSON 文件")
    args = cli.parse_args()

    parsed = _load_parsed(args.parsed_json)
    responder = QAResponder(
        parsed_document=parsed,
        config=QAConfig(mode=args.mode, model=args.model),
    )

    result = responder.answer(question=args.question, current_page=args.page)
    text = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(text)
        print(f"问答完成，结果已保存: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
