#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
构建评测集：eval/eval_set.jsonl

    python eval/build_eval_set.py            # 重新生成评测集并打印统计
    python eval/build_eval_set.py --review   # 另外打印每条事实题的原文上下文，供人工核对

标准答案只用「能被规则客观判定」的事实，不依赖被测系统：

- 枚举题「哪些省提到 X」：某省报告原文出现关键词 X（精确子串）即算提到
- 事实题「X 省 2025 年 GDP 增长目标」：在「预期目标」后 200 字内规则抽取，
  31 省已逐条人工核对；规则抽错的省份写进 OVERRIDES 并注明原因
- 对比题 / 汇总题：复用事实题的标准答案
- 无答案题：经全文检索确认，该省报告里不含该关键词

问法刻意写得多样（"哪些省份……" / "……的省份有哪些" / "列出……"），
模拟真实用户的说法，而不是照着系统的关键词规则去写——
否则意图识别永远是 100%，评测就测不出问题。
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from common import PROVINCES, norm, has_anchored  # noqa: E402

CHUNKS = ROOT / "mvp" / "chunks.json"
OUT = HERE / "eval_set.jsonl"

RANGE = r"\d+(?:\.\d+)?%?[—\-–~～至到]+\d+(?:\.\d+)?%"          # 福建：5.0%—5.5%
SINGLE = r"\d+(?:\.\d+)?%(?:左右|以上|以内)?"                    # 5.5%左右 / 7%以上
TARGET_RE = re.compile(rf"(?:地区生产总值|生产总值|经济)增长(?:{RANGE}|{SINGLE})")

# 规则抽错时在此人工修正：{省份: 证据句}，并写明原因。
# 当前规则（只锚定「预期目标」、支持区间写法）下 31 省人工核对均无误，故为空。
# 迭代记录：初版规则同时锚定「主要目标」，上海/四川/浙江会命中回顾段里的
# 「主要目标任务」，抽到的是 2024 年实际增速；福建的区间目标被截成「5.0%」。
OVERRIDES = {}

# ---------------------------------------------------------------- 题目定义

ENUMERATE = [  # (关键词, 问法, 标签)
    ("低空经济", "哪些省份提到了低空经济", "高覆盖"),
    ("银发经济", "有哪些省把银发经济写进了政府工作报告", "高覆盖"),
    ("以旧换新", "提到以旧换新的省份有哪些", "高覆盖·问法泛化"),
    ("首发经济", "首发经济在哪些省的报告里出现了", "高覆盖"),
    ("新型储能", "哪些省份部署了新型储能", "中覆盖"),
    ("生物制造", "各省报告中，哪些提到了生物制造", "中覆盖"),
    ("冰雪经济", "冰雪经济都有哪些省在发展", "中覆盖"),
    ("海洋经济", "列出提到海洋经济的省份", "中覆盖·问法泛化"),
    ("商业航天", "哪些省份提到了商业航天", "中覆盖"),
    ("人形机器人", "哪些省提到了人形机器人", "低覆盖"),
    ("具身智能", "具身智能被哪几个省写进了报告", "低覆盖"),
    ("脑机接口", "全国有哪些地方提到了脑机接口", "低覆盖"),
    ("预制菜", "哪些省份的报告里提到了预制菜", "低覆盖"),
]

FACT_TEMPLATES = [
    "{p}2025年的GDP增长目标是多少",
    "{p}今年的经济增长预期目标定的多少",
    "{p}2025年地区生产总值预期增长多少",
    "{p}政府工作报告提出的2025年经济增速目标是什么",
]

COMPARE = [  # (省A, 省B, 问法, 可接受的路由类型, 标签)
    ("广东", "江苏", "对比广东和江苏2025年的GDP增长目标", ["comparison"], ""),
    ("河南", "湖北", "河南和湖北今年的经济增长目标有什么不同", ["comparison"], "问法泛化"),
    ("北京", "上海", "比较北京和上海的地区生产总值增长目标", ["comparison"], ""),
    ("四川", "重庆", "四川和重庆2025年经济增速目标对比", ["comparison"], ""),
    ("浙江", "福建", "浙江与福建的GDP预期增长目标有何差异", ["comparison"], "区间目标"),
    ("西藏", "青海", "西藏和青海的经济增长目标分别是多少", ["comparison", "multi_province"], ""),
]

AGGREGATE = [  # (问法, 可接受的路由类型, 标签)
    ("汇总各省2025年GDP增长目标", ["all_provinces", "statistics"], ""),
    ("31个省份2025年的经济增长目标分别是多少", ["all_provinces", "statistics"], "问法泛化"),
]

NEGATIVE = [  # (省份 或 None, 关键词, 问法, 可接受的路由类型)
    (None, "飞行汽车", "哪些省份提到了飞行汽车", ["all_provinces"]),
    ("北京", "低空经济", "北京的政府工作报告提到低空经济了吗", ["single_province"]),
    ("天津", "银发经济", "天津提到了银发经济吗", ["single_province"]),
    ("广东", "冰雪经济", "广东有没有提到冰雪经济", ["single_province"]),
    ("上海", "预制菜", "上海2025年有没有提出发展预制菜", ["single_province"]),
]

# ---------------------------------------------------------------- 标准答案


def num_pattern(v: str) -> str:
    """"5" 与 "5.0" 视为同一个数；"5.5" 不能匹配 "5"。"""
    if re.fullmatch(r"\d+(?:\.0)?", v):
        return re.escape(v.split(".")[0]) + r"(?:\.0)?"
    return re.escape(v)


def answer_regex(evidence: str) -> str:
    """LLM 答案的判分正则：数字 + 限定词（左右/以上）都要对，防止把 2024 年实际值判对。"""
    m = re.search(r"(\d+(?:\.\d+)?)%?[—\-–~～至到]+(\d+(?:\.\d+)?)%", evidence)
    if m:
        return (rf"(?<![\d.]){num_pattern(m.group(1))}%?[—\-–~～至到]+"
                rf"{num_pattern(m.group(2))}%")
    m = re.search(r"(\d+(?:\.\d+)?)%(左右|以上|以内)?", evidence)
    return rf"(?<![\d.]){num_pattern(m.group(1))}%{m.group(2) or ''}"


def build_targets(by_prov):
    targets, problems = {}, []
    for p in PROVINCES:
        chunks = by_prov[p]
        full = norm("".join(c["content"] for c in chunks))
        ev = OVERRIDES.get(p)
        if ev is None:
            for m in re.finditer("预期目标", full):
                g = TARGET_RE.search(full[m.start(): m.start() + 200])
                if g:
                    ev = g.group(0)
                    break
        if ev is None:
            problems.append(f"{p}: 未抽到目标")
            continue
        gold = [c["id"] for c in chunks if has_anchored(norm(c["content"]), ev)]
        if not gold:
            problems.append(f"{p}: 证据句『{ev}』在任何块里都找不到锚点")
        targets[p] = {
            "province": p,
            "evidence": ev,
            "target_text": ev.split("增长", 1)[1],
            "answer_regex": answer_regex(ev),
            "gold_chunks": gold,
        }
    return targets, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="打印事实题原文上下文，供人工核对")
    args = ap.parse_args()

    chunks = json.load(open(CHUNKS, encoding="utf-8"))
    by_prov = defaultdict(list)
    for c in chunks:
        by_prov[c["province"]].append(c)
    for p in by_prov:
        by_prov[p].sort(key=lambda c: c["chunk_id"])
    prov_text = {p: norm("".join(c["content"] for c in by_prov[p])) for p in PROVINCES}

    targets, problems = build_targets(by_prov)
    items = []

    for i, (kw, q, tag) in enumerate(ENUMERATE, 1):
        gt = [p for p in PROVINCES if norm(kw) in prov_text[p]]
        gold = [c["id"] for c in chunks if norm(kw) in norm(c["content"])]
        items.append({"id": f"enum-{i:02d}", "type": "enumerate", "question": q,
                      "expected_types": ["all_provinces"], "keyword": kw,
                      "gt_provinces": gt, "gold_chunks": gold, "tags": tag})

    for i, p in enumerate(PROVINCES, 1):
        items.append({"id": f"fact-{i:02d}", "type": "fact",
                      "question": FACT_TEMPLATES[(i - 1) % len(FACT_TEMPLATES)].format(p=p),
                      "expected_types": ["single_province"], "targets": [targets[p]], "tags": ""})

    for i, (a, b, q, types, tag) in enumerate(COMPARE, 1):
        items.append({"id": f"cmp-{i:02d}", "type": "compare", "question": q,
                      "expected_types": types, "targets": [targets[a], targets[b]], "tags": tag})

    for i, (q, types, tag) in enumerate(AGGREGATE, 1):
        items.append({"id": f"agg-{i:02d}", "type": "aggregate", "question": q,
                      "expected_types": types, "targets": [targets[p] for p in PROVINCES],
                      "tags": tag})

    for i, (p, kw, q, types) in enumerate(NEGATIVE, 1):
        scope = [p] if p else PROVINCES
        leaked = [s for s in scope if norm(kw) in prov_text[s]]
        if leaked:
            problems.append(f"无答案题「{q}」不成立：{leaked} 提到了「{kw}」")
        items.append({"id": f"neg-{i:02d}", "type": "negative", "question": q,
                      "expected_types": types, "keyword": kw, "province": p, "tags": ""})

    if problems:
        print("❌ 标准答案存在问题，未写出评测集：")
        for x in problems:
            print("   -", x)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    count = defaultdict(int)
    for it in items:
        count[it["type"]] += 1
    print(f"✅ 已写出 {len(items)} 题 → {OUT.relative_to(ROOT)}")
    print("   " + " / ".join(f"{k} {v}" for k, v in count.items()))
    cov = [len(it["gt_provinces"]) for it in items if it["type"] == "enumerate"]
    print(f"   枚举题覆盖省数: {sorted(cov, reverse=True)}")
    multi = [p for p, t in targets.items() if len(t["gold_chunks"]) > 1]
    print(f"   事实题金标块: 31 省均已定位；{len(multi)} 省有 2 个（切块重叠所致）")

    if args.review:
        print("\n人工核对：每省「预期目标」证据句及其原文上下文")
        for p in PROVINCES:
            t, full = targets[p], prov_text[p]
            # 定位带锚点的那一处（同一句话可能也出现在回顾段里）
            i = next(m.start() for m in re.finditer(re.escape(t["evidence"]), full)
                     if has_anchored(full[max(0, m.start() - 40): m.end()], t["evidence"]))
            print(f"  {p:<4} {t['target_text']:<12} …{full[max(0, i - 30): i + len(t['evidence']) + 10]}…")


if __name__ == "__main__":
    main()
