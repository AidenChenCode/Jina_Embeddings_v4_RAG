#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一个查询的完整旅程：从 31 份 Word 文档到最终答案。
每一步都打印真实的中间产物。
"""
import sys, json, types
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("jieba", types.ModuleType("jieba"))

QUERY = "河南2025年重点工作有哪些"
BAR = "─" * 70


def sep(n, title):
    print(f"\n{BAR}\n【第 {n} 步】{title}\n{BAR}")


def main():
    # ================================================================
    sep(0, "起点：一份 Word 文档")
    from docx import Document
    f = ROOT / "docs" / "2025年河南省政府工作报告.docx"
    doc = Document(f)
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full = "\n".join(paras)
    print(f"文件：{f.name}")
    print(f"段落数：{len(paras)}    总字数：{len(full):,}")
    print(f"\n开头 3 段：")
    for p in paras[:3]:
        print(f"  · {p[:60]}{'...' if len(p) > 60 else ''}")
    print(f"\n❓ 问题：{len(full):,} 字，31 个省就是 60 万字。")
    print("   大模型一次读不下这么多，就算读得下，成本也高得离谱。")
    print("   → 所以需要 RAG：先找出相关的一小部分，只把这部分给模型。")

    # ================================================================
    sep(1, "切块（Chunking）：把长文切成小段")
    with open(ROOT / "mvp" / "chunks.json", encoding="utf-8") as fp:
        chunks = json.load(fp)
    henan = [c for c in chunks if c["province"] == "河南"]
    print(f"全部 31 省 → {len(chunks)} 个块；其中河南 {len(henan)} 个块")
    print(f"每块约 1000 字，相邻块之间重叠 200 字（防止把一句话切断）\n")
    c0 = henan[3]
    print(f"举例，河南的第 4 个块（{c0['char_count']} 字）：")
    print(f"  id       : {c0['id']}")
    print(f"  province : {c0['province']}      ← 关键！后面按省筛选靠它")
    print(f"  内容前120字：{c0['content'][:120]}...")
    print("\n💡 为什么要切？因为检索的最小单位就是块。")
    print("   切太大 → 塞不下几个，且混入无关内容；切太小 → 句子被腰斩，语义不完整。")

    # ================================================================
    sep(2, "向量化（Embedding）：把文字变成数字")
    texts = [c["content"] for c in chunks]
    vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=60000)
    M = vec.fit_transform(texts)
    print(f"把 {len(texts)} 个块，每个都变成一串数字（向量）")
    print(f"结果是一个矩阵：{M.shape[0]} 行（块） × {M.shape[1]} 列（维度）")
    print(f"\n第一个块的向量长这样（只显示前 8 个非零值）：")
    row = M[0].toarray().ravel()
    nz = np.nonzero(row)[0][:8]
    print("  [" + ", ".join(f"{row[i]:.3f}" for i in nz) + ", ...]")
    print("\n💡 为什么要变成数字？因为计算机没法直接比较两句话像不像，")
    print("   但可以算两串数字的距离。意思越接近的文本，向量距离越近。")
    print("   （真实项目用 Jina Embeddings v4，1024 维；这里用 TF-IDF 演示，原理一致）")

    # ================================================================
    sep(3, "建索引：把向量存起来，方便快速查找")
    print(f"把 {M.shape[0]} 个向量塞进 FAISS 索引（一个专门做向量搜索的库）")
    print("这一步是离线做的，只做一次，结果存到磁盘。")
    print("以后每次查询直接加载，不用重新算。")
    print(f"\n本项目实际存了 3 个文件：")
    print("  faiss_index.bin      ← 向量索引")
    print("  chunks_metadata.pkl  ← 每个块的原文和省份信息")
    print("  embeddings.npy       ← 原始向量")

    # ================================================================
    sep(4, f"检索：用户提问「{QUERY}」")
    print("① 先判断用户想干嘛（意图识别）")
    PROV = ["北京","天津","河北","山西","内蒙古","辽宁","吉林","黑龙江","上海","江苏",
            "浙江","安徽","福建","江西","山东","河南","湖北","湖南","广东","广西",
            "海南","重庆","四川","贵州","云南","西藏","陕西","甘肃","青海","宁夏","新疆"]
    mentioned = [p for p in PROV if p in QUERY]
    print(f"   扫描 query 里有没有省份名 → 找到 {mentioned}")
    print(f"   只提到 1 个省 → 判定为 single_province")
    print(f"   查配置表：单省查询给 30 个块、4 万字预算")

    print("\n② 把问题本身也变成向量")
    qv = vec.transform([QUERY])
    print(f"   「{QUERY}」→ 一个 {qv.shape[1]} 维向量（和块用同一套编码规则）")

    print("\n③ 算这个向量和 855 个块向量的相似度，从高到低排序")
    scores = (M @ qv.T).toarray().ravel()
    order = np.argsort(-scores)
    print(f"   全局最相似的 5 个块：")
    for i in order[:5]:
        print(f"     {scores[i]:.4f}  [{chunks[i]['province']}] {chunks[i]['content'][:38]}...")

    print("\n④ 因为只要河南，把非河南的过滤掉")
    hn_idx = [i for i in order if chunks[i]["province"] == "河南"][:30]
    print(f"   筛出河南的块，取前 30 个 → 实得 {len(hn_idx)} 个")
    print(f"   最相关的 3 个：")
    for i in hn_idx[:3]:
        print(f"     {scores[i]:.4f}  {chunks[i]['content'][:46]}...")

    # ================================================================
    sep(5, "组装上下文：把检索到的块拼成一段文字")
    picked = [chunks[i] for i in hn_idx]
    ctx_parts = [f"\n=== {picked[0]['province']} ==="]
    for c in picked:
        ctx_parts.append(c["content"])
    context = "\n".join(ctx_parts)
    total = sum(c["char_count"] for c in picked)
    print(f"把 {len(picked)} 个块按省份分组拼接 → {total:,} 字")
    print(f"预算是 4 万字，{total:,} 字 {'超了，需要截断' if total > 40000 else '没超，全部保留'}")
    print(f"\n拼出来长这样：")
    print("  " + context[:150].replace("\n", "\n  ") + "...")

    # ================================================================
    sep(6, "生成：把「上下文 + 问题」交给大模型")
    prompt = f"""以下是政府工作报告的相关内容：

{context}

请根据以上内容回答：{QUERY}
要求：必须保留原文中的所有具体数字。"""
    print(f"最终 prompt 结构：")
    print(f"  ├─ 检索到的原文  {total:,} 字")
    print(f"  ├─ 用户的问题    {len(QUERY)} 字")
    print(f"  └─ 输出格式要求  约 30 字")
    print(f"  总计 {len(prompt):,} 字 → 发给硅基流动的 QwenLong-L1-32B")
    print(f"\n💡 关键：模型只看到这 {total:,} 字，看不到另外 30 个省、也看不到河南没被选中的块。")
    print("   所以【检索选得对不对】直接决定了【答案对不对】。")
    print("   模型再强，你没把相关内容捞给它，它也答不出来。")

    print(f"\n{BAR}")
    print("这就是 RAG 的全部：切块 → 向量化 → 存索引 → 检索 → 拼接 → 生成")
    print(BAR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
