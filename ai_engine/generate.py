import argparse
import json
import os

try:
    from .parser import DocumentParser
    from .generator import LessonGenerator, GenerationConfig
except ImportError:
    from parser import DocumentParser
    from generator import LessonGenerator, GenerationConfig


def main() -> None:
    cli = argparse.ArgumentParser(description="从文档生成讲稿与思维导图")
    cli.add_argument("file", help="输入文件路径（.pdf 或 .pptx）")
    cli.add_argument("--mode", default="llm", choices=["mock", "llm"], help="生成模式")
    cli.add_argument("--model", default=os.getenv("AI_MODEL", "qwen-turbo"), help="LLM 模型名（mode=llm 时生效）")
    cli.add_argument("--out", default=None, help="输出 JSON 文件路径")
    args = cli.parse_args()

    parser = DocumentParser(args.file)
    parsed = parser.parse()

    generator = LessonGenerator(
        GenerationConfig(
            mode=args.mode,
            model=args.model,
        )
    )
    generated = generator.generate(parsed)

    output = {
        "parsed": parsed,
        "generated": generated,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(text)
        print(f"生成完成，结果已保存: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
