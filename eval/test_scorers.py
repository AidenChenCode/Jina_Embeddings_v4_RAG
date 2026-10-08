#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
判分规则的自测：python eval/test_scorers.py

LLM 模式的判分是启发式规则（看省名、数字、否定词）。没有 API Key 时
拿不到真实 LLM 答案，这里用构造的答案把每条规则的预期行为钉死，
包括几个容易误判的写法。拿到真实答案后，还应抽样做人工一致性校验。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import Answer, score  # noqa: E402

ZJ = {"province": "浙江", "evidence": "生产总值增长5.5%左右", "target_text": "5.5%左右",
      "answer_regex": r"(?<![\d.])5\.5%左右", "gold_chunks": ["浙江_008", "浙江_009"]}
GD = {"province": "广东", "evidence": "地区生产总值增长5%左右", "target_text": "5%左右",
      "answer_regex": r"(?<![\d.])5(?:\.0)?%左右", "gold_chunks": ["广东_014"]}
JS = {"province": "江苏", "evidence": "地区生产总值增长5%以上", "target_text": "5%以上",
      "answer_regex": r"(?<![\d.])5(?:\.0)?%以上", "gold_chunks": ["江苏_011"]}
ENUM = {"id": "t", "type": "enumerate", "question": "哪些省份提到了低空经济",
        "expected_types": ["all_provinces"], "keyword": "低空经济",
        "gt_provinces": ["广东", "江苏", "浙江", "四川"], "gold_chunks": ["a", "c"]}


def llm(content, qt="all_provinces"):
    return Answer(qt, content, llm=True, retrieved=None, partial=True, latency=0.0)


def digest(content, qt="single_province", retrieved=None):
    return Answer(qt, content, llm=False, retrieved=retrieved or [], partial=False, latency=0.0)


def item(t, targets=None, **kw):
    base = {"id": "t", "type": t, "question": "q", "expected_types": ["single_province"]}
    if targets:
        base["targets"] = targets
    base.update(kw)
    return base


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ---------------------------------------------------------------- 枚举题


@case("枚举·LLM：否定句里的省份不算点名")
def _():
    r = score(ENUM, llm("提到低空经济的省份有：广东、江苏、浙江。\n北京、天津未提及低空经济。"))
    assert r["ans"]["recall"] == 0.75 and r["ans"]["precision"] == 1.0, r["ans"]


@case("枚举·LLM：多报的省份计入精确率")
def _():
    r = score(ENUM, llm("广东、江苏、北京都提到了低空经济。"))
    assert r["ans"]["recall"] == 0.5 and abs(r["ans"]["precision"] - 2 / 3) < 1e-9, r["ans"]
    assert r["ans"]["false_pos"] == ["北京"], r["ans"]


@case("枚举·LLM：同一句里先肯定后否定，逗号切开后分别判断")
def _():
    r = score(ENUM, llm("广东提到了低空经济，北京没有提到"))
    assert r["ans"]["recall"] == 0.25 and r["ans"]["precision"] == 1.0, r["ans"]


@case("枚举·摘编：只有该省小节里出现关键词才算看得到")
def _():
    content = "### 广东\n- ……发展低空经济……\n\n### 江苏\n- ……其他内容……\n"
    retrieved = [{"id": "a", "province": "广东", "content": "发展低空经济"},
                 {"id": "b", "province": "江苏", "content": "其他内容"}]
    r = score(ENUM, digest(content, "all_provinces", retrieved))
    assert r["ans"]["recall"] == 0.25, r["ans"]
    assert r["ret"]["prov_recall"] == 0.25 and r["ret"]["ctx_precision"] == 0.5, r["ret"]
    assert ("广东", True, True) in r["units"] and ("江苏", False, False) in r["units"], r["units"]


# ---------------------------------------------------------------- 事实题


@case("事实·LLM：数字和限定词都对才算对")
def _():
    assert score(item("fact", [ZJ]), llm("浙江2025年生产总值预期增长5.5%左右。", "single_province"))["ans"]["correct"] == 1


@case("事实·LLM：2024 年实际值（无「左右」）不能判对")
def _():
    assert score(item("fact", [ZJ]), llm("浙江2024年生产总值增长5.5%。", "single_province"))["ans"]["correct"] == 0


@case("事实·LLM：全角％和空格不影响判分")
def _():
    assert score(item("fact", [ZJ]), llm("目标为 5.5％ 左右", "single_province"))["ans"]["correct"] == 1


@case("事实·摘编：证据句前要有「预期目标」锚点（防内蒙古式陷阱）")
def _():
    ok = "### 浙江\n- 主要预期目标为：生产总值增长5.5%左右，城镇调查失业率…\n"
    trap = "### 浙江\n- 预计全省生产总值增长5.5%左右，总量突破9万亿元…\n"
    assert score(item("fact", [ZJ]), digest(ok))["ans"]["correct"] == 1
    assert score(item("fact", [ZJ]), digest(trap))["ans"]["correct"] == 0


@case("事实·检索：只拿到部分引用时，金标没出现记为「未知」而非「没检索到」")
def _():
    a = Answer("single_province", "x", llm=True, retrieved=[{"id": "浙江_001", "province": "浙江", "content": ""}],
               partial=True, latency=0.0)
    assert score(item("fact", [ZJ]), a)["units"][0][1] is None


# ---------------------------------------------------------------- 对比题


@case("对比·LLM：表格逐行判断，两省都对")
def _():
    t = "| 省份 | 2025年目标 |\n|---|---|\n| 广东 | 5%左右 |\n| 江苏 | 5%以上 |"
    assert score(item("compare", [GD, JS]), llm(t, "comparison"))["ans"]["correct"] == 1


@case("对比·LLM：两省数字对调（张冠李戴）判为全错")
def _():
    t = "| 省份 | 2025年目标 |\n|---|---|\n| 广东 | 5%以上 |\n| 江苏 | 5%左右 |"
    assert score(item("compare", [GD, JS]), llm(t, "comparison"))["ans"]["correct"] == 0


@case("对比·LLM：分号分隔的叙述句也能逐省判断")
def _():
    t = "广东提出地区生产总值增长5%左右；江苏提出增长5%以上。"
    assert score(item("compare", [GD, JS]), llm(t, "comparison"))["ans"]["correct"] == 1


# ---------------------------------------------------------------- 无答案题

NEG = {"id": "t", "type": "negative", "question": "北京提到低空经济了吗",
       "expected_types": ["single_province"], "keyword": "低空经济", "province": "北京"}


@case("无答案·LLM：明确说没有 → 通过")
def _():
    assert score(NEG, llm("北京的政府工作报告中没有提到低空经济。", "single_province"))["score"] == 1.0


@case("无答案·LLM：编造肯定说法 → 不通过")
def _():
    assert score(NEG, llm("北京提出要大力发展低空经济。", "single_province"))["score"] == 0.0


@case("无答案·LLM：标题和复述问题的句子不算肯定")
def _():
    assert score(NEG, llm("## 北京与低空经济\n北京是否提到低空经济？根据资料，未提及。", "single_province"))["score"] == 1.0


@case("无答案·LLM：含糊其辞、没说「没有」→ 不通过")
def _():
    assert score(NEG, llm("资料有限，建议查阅原文。", "single_province"))["score"] == 0.0


@case("无答案·摘编：不适用，不计分")
def _():
    r = score(NEG, digest("### 北京\n- ……"))
    assert r["score"] is None and r["ans"]["refusal_ok"] is None


# ---------------------------------------------------------------- 其他


@case("请求失败计 0 分并给出原因")
def _():
    a = Answer("", "", True, None, True, 0.0, error="timeout")
    r = score(item("fact", [ZJ]), a)
    assert r["score"] == 0.0 and "timeout" in r["diag"]


@case("路由错误会写进诊断")
def _():
    r = score(item("fact", [ZJ]), llm("增长5.5%左右", "general"))
    assert not r["intent_ok"] and r["diag"].startswith("路由成 general")


if __name__ == "__main__":
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {name}\n      {e}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} 通过")
    sys.exit(1 if failed else 0)
