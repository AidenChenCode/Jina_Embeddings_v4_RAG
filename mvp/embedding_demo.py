#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
"打分"这一步到底在干什么 —— 把 Embedding 拆开看。
"""
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
BAR = "─" * 68


def sep(t):
    print(f"\n{BAR}\n{t}\n{BAR}")


# ====================================================================
sep("实验 1：一句话变成数字后，长什么样")

sents = [
    "大力发展低空经济",      # A
    "推动无人机产业壮大",    # B  ← 和 A 意思接近，但用词几乎不同
    "加强中小学教育质量",    # C  ← 和 A 完全无关
]
for i, s in enumerate(sents):
    print(f"  {chr(65+i)}: {s}")

vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 2))
M = vec.fit_transform(sents)
names = vec.get_feature_names_out()

print(f"\n打分表一共有 {len(names)} 个格子，每个格子对应一个'字的组合':")
print("  " + "  ".join(f"[{n}]" for n in names[:12]) + " ...")

print(f"\nA「{sents[0]}」的分数条：")
row = M[0].toarray().ravel()
for i in np.nonzero(row)[0]:
    bar = "█" * int(row[i] * 30)
    print(f"   [{names[i]}]  {row[i]:.3f}  {bar}")
print("   其他格子全是 0.000（因为这句话里没出现那些字的组合）")

# ====================================================================
sep("实验 2：怎么判断两句话像不像 —— 手算一遍")

a, b, c = (M[i].toarray().ravel() for i in range(3))


def show_sim(x, y, nx, ny):
    shared = [(names[i], x[i], y[i]) for i in range(len(names)) if x[i] > 0 and y[i] > 0]
    score = float(np.dot(x, y))
    print(f"\n  {nx}  ×  {ny}")
    if shared:
        print(f"    两句都有的格子：")
        for n, u, v in shared:
            print(f"      [{n}]  {u:.3f} × {v:.3f} = {u*v:.3f}")
    else:
        print(f"    两句都有的格子：一个都没有")
    print(f"    ── 全部相乘再相加 = 相似度 {score:.4f}")
    return score


s_ab = show_sim(a, b, "A 低空经济", "B 无人机产业")
s_ac = show_sim(a, c, "A 低空经济", "C 中小学教育")

print(f"\n  结论：A和B 得分 {s_ab:.4f}，A和C 得分 {s_ac:.4f}")
print("  ⚠️ A 和 B 明明说的是同一件事，得分却是 0！")
print("     因为这种打分法只会数'有没有相同的字'，不懂意思。")

# ====================================================================
sep("实验 3：真实数据上，这个软肋有多要命")

chunks = json.load(open(ROOT / "mvp" / "chunks.json", encoding="utf-8"))
texts = [c["content"] for c in chunks]
V = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=60000)
X = V.fit_transform(texts)

query = "飞行汽车和送货无人机的产业布局"
print(f"  提问：「{query}」")
print(f"  （报告里管这个叫「低空经济」，但我故意一个字都不提它）\n")

qv = V.transform([query])
scores = (X @ qv.T).toarray().ravel()
order = np.argsort(-scores)[:5]

print("  按'数相同的字'挑出来的前 5 名：")
hit = 0
for r, i in enumerate(order, 1):
    has = "低空经济" in chunks[i]["content"]
    if has:
        hit += 1
    mark = "✅ 真的讲低空经济" if has else "❌ 不相关"
    print(f"   {r}. [{chunks[i]['province']}] {chunks[i]['content'][:30]}...  {mark}")

total = sum(1 for c in chunks if "低空经济" in c["content"])
print(f"\n  ▶ 前 5 名里只有 {hit} 个真的讲低空经济")
print(f"  ▶ 而全部 855 块里，其实有 {total} 块都在讲低空经济")
print("  ▶ 挑错了，是因为它只会数字，不懂'无人机'和'低空经济'是一回事")

# ====================================================================
sep("实验 4：那真正的 Embedding 模型强在哪")

print("""
  上面用的叫 TF-IDF，它的每个格子都有名字（就是某两个字的组合），
  所以你能看懂。但它只会数字面，不懂意思。

  这个项目真正用的 Jina Embeddings v4 不一样：

    · 它有 1024 个格子，但这些格子【没有名字】
    · 没人规定第 37 个格子代表什么，是模型自己从海量文本里学出来的
    · 学完之后，"低空经济" 和 "无人机产业" 的 1024 个数字会很接近，
      哪怕它们一个相同的字都没有

  这就是它值 7.5GB 的原因 —— 那 7.5GB 装的全是"什么和什么是一个意思"。
""")

print(BAR)
print("一句话总结：打分 = 把文字翻译成数字，让电脑能用算术比较意思。")
print("打分表越聪明，挑出来的资料越准。")
print(BAR)
