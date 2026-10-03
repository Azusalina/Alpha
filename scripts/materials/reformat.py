"""Offline reading-copy formatter. No translator/model/DB imports or training.

Preserve source order and wording; normalize layout only. Section boundaries
are supplied explicitly, not inferred authorship or mental-state predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path


def reading_copy(source: Path, output: Path, sections: list[tuple[int, str]],
                 self_speaker: str | None = None) -> dict:
    if source.suffix.lower() not in {".txt", ".md"} or not source.is_file():
        raise ValueError("source must be an existing UTF-8 txt/md file")
    if source.stat().st_size > 4_000_000:
        raise ValueError("source exceeds the current file input size bound")
    original = source.read_bytes()
    text = original.decode("utf-8-sig", errors="strict")
    if not text.strip() or len(text) > 1_000_000 or "\0" in text:
        raise ValueError("source must contain 1..1000000 characters without NUL")
    lines = text.splitlines()
    starts = [start for start, _ in sections]
    if (not starts or starts[0] != 1 or starts != sorted(set(starts))
            or starts[-1] > len(lines) or any(not title.strip() for _, title in sections)):
        raise ValueError("sections must start at line 1 and have increasing valid line numbers")
    if output.suffix.lower() != ".md" or output.exists() or output.is_symlink():
        raise ValueError("output must be a new .md file; overwrite is forbidden")
    digest = hashlib.sha256(original).hexdigest()
    header = [
        "# 材料整理版（阅读／分段审核用）", "",
        f"- 原文件：`{source.name}`；原始 SHA-256：`{digest}`。",
        "- 按用户说明属于自述和日记；不据此判断每条转述／引文均为认可立场。",
        "- 保留原顺序、措辞、日期写法、昵称和不确定语句；只整理空行、缩进和章节。",
        "- 未导入、未预览、未训练、未设置 immediate／confirm 或情境状态。",
        "- 此文件是阅读副本，不是可自动批准的训练包；章节不会自动创建独立 source。",
        "- 后续应分别审核日记／聊天／哲学材料及 rational／emotional／crazy 状态。",
        "- 来源行号指向原文件；本副本的字符 span 已改变，不能复用原文的 span。",
    ]
    if self_speaker:
        header.append(f"- 已确认本人聊天昵称：`{self_speaker}`；其余昵称不合并、不推定。")
    header += ["", "## 目录", ""]
    for number, (start, title) in enumerate(sections, 1):
        end = starts[number] - 1 if number < len(starts) else len(lines)
        header.append(f"- 第 {number:02d} 节：{title}（原文件 {start}–{end} 行）")
    chunks = ["\n".join(header)]
    bodies: list[str] = []
    for number, (start, title) in enumerate(sections, 1):
        end = starts[number] - 1 if number < len(starts) else len(lines)
        body: list[str] = []
        for line in lines[start - 1:end]:
            # Layout only: keep every non-whitespace character in source order.
            line = line.expandtabs(4).rstrip()
            if line.strip():
                body.append(line)
            elif body and body[-1] != "":
                body.append("")
        while body and body[-1] == "":
            body.pop()
        bodies.append("\n".join(body))
        chunks.append(f"## 第 {number:02d} 节 · {title}\n\n"
                      f"原文件行号：{start}–{end}。分节仅为阅读导航，不是模型推断。\n\n"
                      + bodies[-1])
    # Formatting invariant, not a translator/model test: no wording is lost.
    if "".join(text.split()) != "".join("\n".join(bodies).split()):
        raise ValueError("formatting would change non-whitespace source content")
    rendered = "\n\n---\n\n".join(chunks) + "\n"
    if len(rendered) > 1_000_000 or len(rendered.encode("utf-8")) > 4_000_000:
        raise ValueError("reading copy exceeds the current input size bound")
    # Exclusive creation, restrictive permissions; no backup, DB or network access.
    with open(output, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(rendered)
    return {"source_sha256": digest, "sections": len(sections), "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--section", action="append", required=True, help="START_LINE:TITLE")
    parser.add_argument("--self-speaker")
    args = parser.parse_args()
    try:
        sections = [(int(item.split(":", 1)[0]), item.split(":", 1)[1]) for item in args.section]
        result = reading_copy(args.source, args.output, sections, args.self_speaker)
    except (OSError, UnicodeError, ValueError, IndexError):
        parser.exit(1, "unable to create reading copy; check encoding, boundaries and new output path\n")
    # Only aggregate metadata, never private text or inferred parameters.
    print(f"reading copy saved: {result['output']}; sections={result['sections']}; no model invoked")


if __name__ == "__main__":
    main()
