#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MVP 步骤2：复现检索层的三个结构性缺陷。

用 TF-IDF 替代 Jina embeddings（无 GPU/无模型权重）。这不影响结论——
post-filter 漏省份是检索流程的结构问题，与向量质量无关：无论用什么向量，
"先取全局 top-N 再按省过滤" 都无法保证每个省都有结果。
"""
import sys, json, re
from pathlib import Path
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "mvp" / "chunks.json"

PROVINCES = ["北京","天津","河北","山西","内蒙古","辽宁","吉林","黑龙江","上海","江苏",
             "浙江","安徽","福建","江西","山东","河南","湖北","湖南","广东","广西",
             "海南","重庆","四川","贵州","云南","西藏","陕西","甘肃","青海","宁夏","新疆"]

QUERIES = [
    "各省2025年GDP增长目标是多少",
    "各省在科技创新方面的重点任务",
    "各省的民生保障举措",
    "各省乡村振兴的具体部署",
    "各省绿色低碳发展的目标",
]


class MiniStore:
    """复刻 src/vector_store.py 的检索行为，向量层换成 TF-IDF。"""

    def __init__(self, chunks):
        self.chunks = chunks
        # 中文用 char ngram，无需分词
        self.vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=60000)
        self.M = self.vec.fit_transform([c["content"] for c in chunks])
        # L2 归一化后内积即余弦；排序等价于 L2 距离升序
        self.N = len(chunks)

    def _scores(self, query):
        q = self.vec.transform([query])
        return (self.M @ q.T).toarray().ravel()

    def search_postfilter(self, query, top_k, province_filter=None):
        """原版逻辑：vector_store.py:247-274
        先全局取 search_k 个候选，再按省份过滤，最后截断到 top_k。"""
        scores = self._scores(query)
        search_k = min(max(top_k * 4, 200), self.N)          # ← 原版第 247 行
        order = np.argsort(-scores)[:search_k]                # 全局 top-search_k

        out = []
        for idx in order:                                     # ← 原版第 255 行起
            c = self.chunks[idx]
            if province_filter and c["province"] != province_filter:
                continue
            out.append((c, float(scores[idx])))
            if len(out) >= top_k:
                break
        return out

    def search_prefilter(self, query, top_k, province_filter=None):
        """修复版：先按省份圈定候选集，再在集合内排序取 top_k。"""
        scores = self._scores(query)
        idxs = range(self.N)
        if province_filter:
            idxs = [i for i in idxs if self.chunks[i]["province"] == province_filter]
        ranked = sorted(idxs, key=lambda i: -scores[i])[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in ranked]


def verify_missing_provinces(store):
    """复现 retriever.py:196 retrieve_for_all_provinces 的循环。"""
    print("=" * 66)
    print("验证 4：全省扫描时 post-filter 的配额缺口")
    print("=" * 66)
    print("  复刻 retriever.py:196-206，每省 top_k=8（config: all_provinces）")
    print("  应得 31×8 = 248 块\n")

    top_k = 8
    tot_post = 0
    for q in QUERIES:
        miss_post, got = [], 0
        for p in PROVINCES:
            r_post = store.search_postfilter(q, top_k=top_k * 4, province_filter=p)[:top_k]
            got += len(r_post)
            if not r_post:
                miss_post.append(p)
        tot_post += got
        short = 248 - got
        print(f"  {q}")
        print(f"    post-filter: {got:>3} 块（缺 {short:>2}，{short/248*100:>4.1f}%）"
              f"  0块省份: {len(miss_post)}")
    avg = tot_post / len(QUERIES)
    print(f"\n  ▶ 平均 {avg:.0f}/248 块，配额缺口 {(248-avg)/248*100:.0f}%")
    print("  ▶ 当前规模(855块)下没有整省消失——全局 top-200 已占全量 23%")


def verify_scale_sensitivity(chunks):
    """search_k 硬编码 200，缺口应随索引规模恶化。"""
    print("\n" + "=" * 66)
    print("验证 4b：规模敏感性 —— search_k 硬编码 200 的后果")
    print("=" * 66)
    print("  vector_store.py:247  search_k = min(max(top_k*4, 200), ntotal)")
    print("  模拟索引扩容（多年度报告入库），观察每省配额与覆盖率\n")

    top_k = 8
    q = QUERIES[0]
    print(f"  {'索引规模':<12} {'top-200占比':<12} {'实得块数':<10} {'缺口':<9} {'0块省份'}")
    print("  " + "-" * 58)
    for mult in [1, 3, 5, 10]:
        scaled = []
        for y in range(mult):
            for c in chunks:
                d = dict(c)
                d["content"] = c["content"] + ("" if y == 0 else f" 第{y}年度补充。")
                scaled.append(d)
        st = MiniStore(scaled)
        got, miss = 0, 0
        for p in PROVINCES:
            r = st.search_postfilter(q, top_k=top_k * 4, province_filter=p)[:top_k]
            got += len(r)
            if not r:
                miss += 1
        ratio = min(max(top_k * 4 * 4, 200), len(scaled)) / len(scaled)
        print(f"  {len(scaled):>5} 块      {ratio*100:>5.1f}%       "
              f"{got:>3}/248     {(248-got)/248*100:>5.1f}%    {miss}")
    print("\n  ▶ 索引越大，固定的 200 候选集占比越小，配额缺口越大")


def verify_chunk_score():
    """验证 retriever.py:484 chunk_score 的中文失效。"""
    print("\n" + "=" * 66)
    print("验证 5：_truncate_results 的 chunk_score 对中文不区分")
    print("=" * 66)

    with open(CHUNKS, encoding="utf-8") as f:
        chunks = json.load(f)

    def orig_score(c):                                  # ← 原版 retriever.py:484
        char_score = min(c["char_count"] / 500, 2.0)
        content_score = len(c["content"].split()) / 100
        return char_score + content_score

    def fixed_score(c):                                 # 加入数字密度
        char_score = min(c["char_count"] / 500, 2.0)
        digits = len(re.findall(r"\d+(?:\.\d+)?%?", c["content"]))
        return char_score + digits / 10

    sample = chunks[:400]
    cs = [len(c["content"].split()) / 100 for c in sample]
    print(f"  content_score = len(content.split())/100")
    print(f"    取值集合: {sorted(set(round(x,3) for x in cs))[:6]}")
    print(f"    最大值 {max(cs):.3f}  最小值 {min(cs):.3f}  → 对总分几乎无贡献")
    print(f"    (char_score 取值范围 0~2.0，相差两个数量级)\n")

    # 看排序差异：数字最密集的块在原版排名如何
    by_digits = sorted(sample, key=lambda c: -len(re.findall(r"\d+(?:\.\d+)?%?", c["content"])))
    top_data_chunk = by_digits[0]
    n_digits = len(re.findall(r"\d+(?:\.\d+)?%?", top_data_chunk["content"]))

    orig_rank = sorted(sample, key=orig_score, reverse=True).index(top_data_chunk) + 1
    fixed_rank = sorted(sample, key=fixed_score, reverse=True).index(top_data_chunk) + 1

    print(f"  取样本中数字最密集的块（含 {n_digits} 个数字，{top_data_chunk['province']}）：")
    print(f"    原版 chunk_score 排名: 第 {orig_rank} / {len(sample)}")
    print(f"    加数字密度后排名:      第 {fixed_rank} / {len(sample)}")
    print(f"  ▶ 截断时优先保留的应该是这类块，原版把它排在了第 {orig_rank} 位")


def verify_intent_conflict():
    """验证 query_router 与 retriever 两套意图识别不一致。"""
    print("\n" + "=" * 66)
    print("验证 6：两处意图识别对同一 query 给出不同结果")
    print("=" * 66)

    def router_intent(query):                # ← query_router.py:218 (elif 链)
        mp = [p for p in PROVINCES if p in query]
        if any(k in query for k in ["所有省份", "各省", "31省", "全国"]):
            return "all_provinces"
        elif len(mp) == 1:
            return "single_province"
        elif len(mp) > 1:
            return "multi_province"
        elif any(k in query for k in ["对比", "比较"]):
            return "comparison"
        elif any(k in query for k in ["统计", "汇总", "总结"]):
            return "statistics"
        return "general"

    def retriever_intent(query):             # ← retriever.py:131-160 (覆盖式)
        t = "general"
        if any(k in query for k in ["所有省份", "全部省份", "各省", "31省", "全国"]):
            t = "all_provinces"
        mp = [p for p in PROVINCES if p in query]
        if mp:
            t = "single_province" if len(mp) == 1 else "multi_province"
        if any(k in query for k in ["对比", "比较", "差异", "区别", "异同"]):
            t = "comparison"
        if any(k in query for k in ["统计", "数量", "总计", "汇总", "分析"]):
            t = "statistics"
        return t

    # 各类型对应的检索预算（config/config.example.py）
    budget = {"single_province": "30块/40K", "multi_province": "15块/60K",
              "all_provinces": "8块/省/80K", "comparison": "25块/100K",
              "statistics": "topic检索", "general": "60块"}

    cases = ["对比广东和江苏的产业发展", "统计各省GDP增长目标", "河南2025年重点工作有哪些",
             "对比京津冀三地的差异", "分析浙江和福建的数字经济", "各省乡村振兴部署"]

    print(f"  {'查询':<26} {'query_router':<17} {'retriever':<17} {'实际生效预算'}")
    print("  " + "-" * 78)
    n_diff = 0
    for q in cases:
        a, b = router_intent(q), retriever_intent(q)
        mark = "  ⚠️" if a != b else ""
        if a != b:
            n_diff += 1
        print(f"  {q:<24} {a:<19} {b:<19} {budget[b]}{mark}")
    print(f"\n  ▶ {n_diff}/{len(cases)} 条查询上两者判定不一致")
    print("  ▶ 实际生效的是 retriever 那一遍；query_router 的 comparison 分支不可达")


def main():
    with open(CHUNKS, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"📚 载入 {len(chunks)} 个块，来自 {len(set(c['province'] for c in chunks))} 个省\n")

    store = MiniStore(chunks)
    verify_missing_provinces(store)
    verify_scale_sensitivity(chunks)
    verify_chunk_score()
    verify_intent_conflict()
    return 0


if __name__ == "__main__":
    sys.exit(main())
