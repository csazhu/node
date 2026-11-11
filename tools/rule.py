"""AGENTS.md §6 规则清单的自动维护工具。

用法：
    python tools/rule.py add "新规则正文" [--tag 分类]
    python tools/rule.py list

规则自动编号、按日期戳记、正文去重；可直接由 AI 或命令行调用。
"""

import argparse
import re
from datetime import date
from pathlib import Path

AGENTS_PATH = Path(__file__).resolve().parents[1] / "AGENTS.md"
START = "<!-- RULES:START -->"
END = "<!-- RULES:END -->"
LINE_RE = re.compile(r"^- R(\d{3}) \[(\d{4}-\d{2}-\d{2})\](?: `([^`]+)`)? (.+)$")


def _split(path):
    text = Path(path).read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError("AGENTS.md 缺少 RULES 标记，无法维护规则清单")
    before, rest = text.split(START, 1)
    block, after = rest.split(END, 1)
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    return before, lines, after


def _body(line):
    m = LINE_RE.match(line)
    return m.group(4).strip() if m else line.lstrip("- ").strip()


def _key(text):
    """去重键：忽略所有空白差异。"""
    return "".join(str(text).split())


def list_rules(path=AGENTS_PATH):
    """返回规则清单的原始行列表。"""
    _, lines, _ = _split(path)
    return lines


def add_rule(text, path=AGENTS_PATH, tag=None, today=None):
    """追加一条规则；正文重复时不写入。返回 (status, line)。"""
    before, lines, after = _split(path)
    body = " ".join(str(text).split())
    if not body:
        raise ValueError("规则正文不能为空")
    for line in lines:
        if _key(_body(line)) == _key(body):
            return "duplicate", line

    nums = []
    for line in lines:
        m = LINE_RE.match(line)
        if m:
            nums.append(int(m.group(1)))
    num = max(nums, default=0) + 1
    stamp = today or date.today().isoformat()
    tag_part = f" `{tag}`" if tag else ""
    new_line = f"- R{num:03d} [{stamp}]{tag_part} {body}"
    lines.append(new_line)

    content = f"{before}{START}\n" + "\n".join(lines) + f"\n{END}{after}"
    Path(path).write_text(content, encoding="utf-8")
    return "added", new_line


def main(argv=None):
    parser = argparse.ArgumentParser(description="维护 AGENTS.md 规则清单")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="追加一条规则（自动编号、去重）")
    p_add.add_argument("text", help="规则正文")
    p_add.add_argument("--tag", help="可选分类标签")
    sub.add_parser("list", help="列出全部规则")
    args = parser.parse_args(argv)

    if args.cmd == "add":
        status, line = add_rule(args.text, tag=args.tag)
        print(("已加入: " if status == "added" else "已存在，跳过: ") + line)
    else:
        for line in list_rules():
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
