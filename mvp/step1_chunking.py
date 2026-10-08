#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MVP 步骤1：用项目原版切块逻辑处理真实数据，验证 chunk_type 分类假设。

不改动 src/data_processor.py，直接复用其 GovernmentReportProcessor。
"""
import sys, json, types
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# data_processor.py 顶部 import jieba，但全项目零调用；且 jieba==0.42.1
# 在新版 setuptools 下无法构建。注入 stub 以避免修改源码。
sys.modules.setdefault("jieba", types.ModuleType("jieba"))

from data_processor import GovernmentReportProcessor  # noqa: E402

DOCS = ROOT / "docs"
OUT = ROOT / "mvp" / "chunks.json"


def main():
    proc = GovernmentReportProcessor(str(DOCS), chunk_size=1000, chunk_overlap=200)
    chunks = proc.process_all_documents()

    if not chunks:
        print("❌ 没有产出任何块")
        return 1

    print("\n" + "=" * 62)
    print("验证 1：chunk_type 分布（README 声称有 title/content/target/summary 四类）")
    print("=" * 62)
    types = Counter(c.chunk_type for c in chunks)
    total = len(chunks)
    for t in ["target", "content", "title", "summary"]:
        n = types.get(t, 0)
        print(f"  {t:<8} {n:>5} 块  {n / total * 100:>5.1f}%")
    print(f"  {'合计':<8} {total:>5} 块")

    print("\n" + "=" * 62)
    print("验证 2：省份识别覆盖率")
    print("=" * 62)
    provs = Counter(c.province for c in chunks)
    unknown = provs.get("未知", 0)
    print(f"  识别出省份数: {len([p for p in provs if p != '未知'])} / 31")
    print(f"  未知省份的块: {unknown}")
    if unknown:
        print("  ⚠️ 存在无法归属省份的块，这些内容在按省检索时永远取不到")

    print("\n" + "=" * 62)
    print("验证 3：块长度分布（title 判定条件是 len < 100）")
    print("=" * 62)
    lens = sorted(c.char_count for c in chunks)
    import statistics
    print(f"  最短 {lens[0]}  中位 {statistics.median(lens):.0f}  最长 {lens[-1]}")
    under100 = sum(1 for x in lens if x < 100)
    print(f"  长度 < 100 的块: {under100} 个 ({under100 / total * 100:.1f}%)")
    print("  → 这是 chunk_type 能被判为 'title' 的必要条件")

    # 落盘供后续步骤复用
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in chunks], f, ensure_ascii=False)
    print(f"\n💾 已保存 {total} 个块 → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
