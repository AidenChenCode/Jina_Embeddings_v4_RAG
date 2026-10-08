#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 评测：意图 → 检索 → 答案 三层打分，再做信息点级归因。

    python eval/run_eval.py                                # 进程内评测 Demo 后端（无需 GPU / Key）
    python eval/run_eval.py --api http://127.0.0.1:8000    # 评测正在运行的服务（Demo 或完整模式）
    python eval/run_eval.py --out eval/reports/某次.md      # 报告另存一份
    python eval/run_eval.py --types enumerate,fact         # 只跑部分题型
    python eval/run_eval.py --dump eval/reports/某次.jsonl  # 导出逐题明细，便于对比两次评测

答案判分随生成方式自动切换：
- 摘编模式（Demo 未配 Key）：答案是原文片段，判「用户能否在答案里看到证据」
- LLM 模式（配了 Key，或完整系统）：判「答案是否明确给出了正确内容」，规则是启发式的，
  见 llm_* 函数；正式使用前应抽样人工复核，算出与人工判断的一致率

两种后端拿到的检索结果不同：
- 进程内 Demo：拿到完整检索结果，检索层指标都能算
- HTTP 接口：只拿到返回的前 12 条引用来源，枚举/对比/汇总题的检索指标记为「—」，
  事实题的排名只在前 12 条内有效（即 MRR@12）
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from common import PROVINCES, norm, has_anchored, segments, is_negated  # noqa: E402

EVAL_SET = HERE / "eval_set.jsonl"
TYPE_LABEL = {"enumerate": "枚举题", "fact": "事实题", "compare": "对比题",
              "aggregate": "汇总题", "negative": "无答案题"}


# ====================================================================== 后端


@dataclass
class Answer:
    query_type: str
    content: str
    llm: bool                       # 答案是否由 LLM 生成（否则是摘编）
    retrieved: Optional[list]       # [{id, province, content}]，按分数降序
    partial: bool                   # True：retrieved 只是接口返回的前若干条引用
    latency: float
    error: Optional[str] = None


class DemoBackend:
    """进程内调用 DemoRAG，能拿到完整检索结果。"""

    def __init__(self):
        sys.path.insert(0, str(ROOT))
        from API_KIT.demo_rag import DemoRAG
        self.rag = DemoRAG()
        llm = "LLM 生成" if self.rag.api_key else "摘编模式"
        self.label = f"Demo 后端 · 进程内 · TF-IDF 检索 · {llm}"

    def ask(self, q: str) -> Answer:
        _, results = self.rag.retrieve(q)          # 与 query() 内部是同一条检索路径
        t0 = time.time()
        resp = self.rag.query(q)
        return Answer(
            query_type=resp.get("query_type", ""),
            content=resp.get("content", ""),
            llm=bool(resp.get("llm_used")),
            retrieved=[{"id": c["id"], "province": c["province"], "content": c["content"]}
                       for c, _ in results],
            partial=False,
            latency=time.time() - t0,
            error=None if resp.get("success") else resp.get("error", "查询失败"),
        )


class ApiBackend:
    """通过 HTTP 评测任意一个兼容接口的服务（web_server.py 或 api_server.py）。"""

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        mode = "未知"
        try:
            with urllib.request.urlopen(f"{self.url}/api/status", timeout=10) as r:
                d = json.load(r).get("data") or {}
            mode = {"demo": "Demo 模式", "full": "完整系统"}.get(d.get("mode"), d.get("mode", "未知"))
        except Exception:
            pass
        self.label = f"HTTP 接口 · {self.url} · {mode}"

    def ask(self, q: str) -> Answer:
        req = urllib.request.Request(
            f"{self.url}/api/query", data=json.dumps({"query": q}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=200) as r:
                resp = json.load(r)
        except Exception as e:
            return Answer("", "", True, None, True, time.time() - t0, error=str(e))
        data = resp["data"] if isinstance(resp.get("data"), dict) else resp
        digest = data.get("mode") == "demo" and not data.get("llm_used")
        sources = [{"id": s.get("id"), "province": s.get("province"), "content": s.get("excerpt", "")}
                   for s in (data.get("sources") or [])]
        return Answer(
            query_type=data.get("query_type", ""),
            content=data.get("content", "") or "",
            llm=not digest,
            retrieved=sources,
            partial=True,
            latency=time.time() - t0,
            error=None if resp.get("success", True) else resp.get("error", "查询失败"),
        )


# ====================================================================== 判分


def digest_sections(content: str) -> dict:
    """摘编答案按「### 省份」切成 {省份: 该节文字(已 norm)}。"""
    out = {}
    for part in re.split(r"^### ", content or "", flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        out[head.strip()] = norm(body)
    return out


def _is_claim(seg: str) -> bool:
    """排除标题行和复述问题的句子，它们不是在下结论。"""
    s = seg.strip()
    return not (s.startswith("#") or "是否" in s or s.endswith("吗"))


def llm_affirmed_provinces(content: str) -> set:
    """LLM 答案中以肯定语气点名的省份（否定句里出现的不算）。"""
    named = set()
    for seg in segments(content, fine=True):
        if _is_claim(seg) and not is_negated(seg):
            named.update(p for p in PROVINCES if p in seg)
    return named


def llm_target_ok(content: str, target: dict, single: bool) -> bool:
    """单省题：全文出现正确的「数字+限定词」即可；
    多省题：省名和正确数字必须出现在同一句/同一行，防止张冠李戴。"""
    pat = re.compile(target["answer_regex"])
    if single:
        return bool(pat.search(norm(content)))
    return any(target["province"] in s and pat.search(norm(s)) for s in segments(content))


def llm_refusal_ok(content: str, keyword: str) -> bool:
    """无答案题：明确说了「没有」，且没有任何一句肯定地提到该关键词。"""
    segs = [s for s in segments(content, fine=True) if _is_claim(s)]
    said_no = any(is_negated(s) for s in segs)
    affirmed = any(keyword in s and not is_negated(s) for s in segs)
    return said_no and not affirmed


def gold_rank(retrieved: list, gold_ids: list) -> Optional[int]:
    gold = set(gold_ids)
    for i, r in enumerate(retrieved, 1):
        if r["id"] in gold:
            return i
    return None


def score(item: dict, ans: Answer) -> dict:
    """单题打分。units 是信息点级的 (名称, 是否检索到 True/False/None, 是否答出)。"""
    t = item["type"]
    rec = {"id": item["id"], "type": t, "question": item["question"], "tags": item.get("tags", ""),
           "query_type": ans.query_type, "expected_types": item["expected_types"],
           "intent_ok": ans.query_type in item["expected_types"], "latency": ans.latency,
           "llm": ans.llm, "ret": {}, "ans": {}, "units": [], "score": None, "diag": ""}
    if ans.error:
        rec.update(score=0.0, diag=f"请求失败：{ans.error}")
        return rec

    retrieved = ans.retrieved
    complete = retrieved is not None and not ans.partial
    sections = None if ans.llm else digest_sections(ans.content)

    if t == "enumerate":
        kw, gt = item["keyword"], item["gt_provinces"]
        hit = None
        if complete:
            k = norm(kw)
            hit = {r["province"] for r in retrieved if k in norm(r["content"])} & set(gt)
            gold = set(item["gold_chunks"])
            got = sum(r["id"] in gold for r in retrieved)
            rec["ret"] = {"prov_recall": len(hit) / len(gt), "chunk_recall": got / len(gold),
                          "ctx_precision": got / len(retrieved) if retrieved else 0.0,
                          "n": len(retrieved)}
        if ans.llm:
            named = llm_affirmed_provinces(ans.content)
            shown = named & set(gt)
            rec["ans"] = {"recall": len(shown) / len(gt),
                          "precision": len(shown) / len(named) if named else None,
                          "false_pos": sorted(named - set(gt))}
        else:
            shown = {p for p in gt if norm(kw) in sections.get(p, "")}
            rec["ans"] = {"recall": len(shown) / len(gt), "precision": None, "false_pos": []}
        rec["units"] = [(p, None if hit is None else p in hit, p in shown) for p in gt]
        rec["score"] = rec["ans"]["recall"]
        rec["diag"] = (f"应有 {len(gt)} 省；"
                       + (f"检索结果里有证据 {len(hit)} 省；" if hit is not None else "")
                       + f"答案里{'给出' if ans.llm else '看得到'} {len(shown)} 省"
                       + (f"；多报 {rec['ans']['false_pos']}" if rec["ans"]["false_pos"] else ""))

    elif t in ("fact", "compare", "aggregate"):
        ranks, parts = [], []
        for tg in item["targets"]:
            rank = gold_rank(retrieved, tg["gold_chunks"]) if retrieved is not None else None
            if rank is not None:
                got = True
            elif complete:
                got = False
            else:
                got = None                      # 只拿到前 12 条：没出现不等于没检索到
            ok = (llm_target_ok(ans.content, tg, single=(t == "fact")) if ans.llm
                  else has_anchored(sections.get(tg["province"], ""), tg["evidence"]))
            rec["units"].append((tg["province"], got, ok))
            ranks.append(rank)
            where = f"第{rank}" if rank else ("未检索到" if complete else "不在前12")
            parts.append(f"{tg['province']} {tg['target_text']}（金标{where}）{'✓' if ok else '✗'}")
        n_ok = sum(u[2] for u in rec["units"])
        # 只拿到接口返回的前若干条引用时，条数不代表真实检索数量，不报
        rec["ret"] = {"ranks": ranks, "n": len(retrieved) if complete else None, "complete": complete}
        rec["ans"] = {"correct": n_ok / len(rec["units"])}
        rec["score"] = rec["ans"]["correct"]
        if t == "aggregate":
            n_got = sum(u[1] is True for u in rec["units"])
            rec["diag"] = f"31 省中：检索结果含金标 {n_got} 省，答案给出 {n_ok} 省"
        else:
            n = rec["ret"]["n"]
            rec["diag"] = "；".join(parts) + (f"（共返回 {n} 块）" if t == "fact" and n else "")

    elif t == "negative":
        if ans.llm:
            ok = llm_refusal_ok(ans.content, item["keyword"])
            rec["ans"] = {"refusal_ok": ok}
            rec["score"] = float(ok)
            rec["diag"] = "正确说明了没有" if ok else "没有明确说「没有」，或出现了肯定说法"
        else:
            rec["ans"] = {"refusal_ok": None}
            rec["diag"] = "摘编模式只能罗列原文，无法表达「没有」"

    if not rec["intent_ok"]:
        rec["diag"] = f"路由成 {ans.query_type}（应为 {'/'.join(item['expected_types'])}）；" + rec["diag"]
    return rec


# ====================================================================== 汇总与报告


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def num(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def summarize(recs: list) -> dict:
    by = defaultdict(list)
    for r in recs:
        by[r["type"]].append(r)
    S = {"n": len(recs), "by": by}

    E = by["enumerate"]
    S["enum"] = {k: mean(r["ret"].get(k) for r in E) for k in ("prov_recall", "chunk_recall", "ctx_precision")}
    S["enum"]["ans_recall"] = mean(r["ans"].get("recall") for r in E)
    S["enum"]["ans_precision"] = mean(r["ans"].get("precision") for r in E)

    F = by["fact"]
    ranks = [r["ret"]["ranks"][0] for r in F if r["ret"].get("ranks")]
    S["fact"] = {"mrr": mean([1 / k if k else 0 for k in ranks]),
                 "n_ret": mean(r["ret"].get("n") for r in F),
                 "acc": mean(r["ans"].get("correct") for r in F)}
    for k in (1, 3, 5):
        S["fact"][f"hit{k}"] = mean([bool(x and x <= k) for x in ranks])

    # 对比 / 汇总题的检索指标需要完整检索结果；HTTP 模式只有前 12 条引用，不报
    C = by["compare"]
    S["cmp"] = {"both": mean([all(x is not None for x in r["ret"]["ranks"])
                              for r in C if r["ret"].get("complete")]),
                "acc": mean(r["ans"].get("correct") for r in C)}

    A = by["aggregate"]
    S["agg"] = {"ret": mean([sum(u[1] is True for u in r["units"]) / len(r["units"])
                             for r in A if r["ret"].get("complete")]),
                "acc": mean(r["ans"].get("correct") for r in A)}

    S["neg"] = mean(r["ans"].get("refusal_ok") for r in by["negative"])
    lat = sorted(r["latency"] for r in recs)
    S["p50"] = statistics.median(lat) if lat else None
    S["p90"] = lat[min(len(lat) - 1, int(len(lat) * 0.9))] if lat else None
    return S


def attribution(recs: list) -> dict:
    """信息点级归因：每个信息点落到 检索 × 答案 的一个格子里。"""
    table = defaultdict(Counter)
    for r in recs:
        for _, got, ok in r["units"]:
            if got is None:
                cell = "unknown_ok" if ok else "unknown_miss"
            elif got and ok:
                cell = "ok"
            elif got:
                cell = "gen_loss"
            elif ok:
                cell = "no_ret_but_ok"
            else:
                cell = "ret_loss"
            table[r["type"]][cell] += 1
    return table


def render(recs: list, backend_label: str, answer_mode: str) -> str:
    S = summarize(recs)
    A = attribution(recs)
    by = S["by"]
    L = []
    w = L.append

    counts = " / ".join(f"{TYPE_LABEL[t]} {len(by[t])}" for t in TYPE_LABEL if by[t])
    w("# RAG 评测报告\n")
    w(f"- **被测系统**：{backend_label}")
    w(f"- **答案判分方式**：{answer_mode}")
    w(f"- **评测集**：`eval/eval_set.jsonl`，{S['n']} 题（{counts}）")
    w(f"- **时间**：{datetime.now():%Y-%m-%d %H:%M}\n")

    w("## 一、总览\n")
    w("| 层 | 指标 | 结果 | 含义 |")
    w("|---|---|---|---|")
    n_ok = sum(r["intent_ok"] for r in recs)
    w(f"| 意图 | 路由准确率 | {n_ok}/{len(recs)}（{pct(n_ok / len(recs))}） | 问题被分到正确的检索策略 |")
    if by["enumerate"]:
        e = S["enum"]
        w(f"| 检索 | 枚举题·省份召回率 | {pct(e['prov_recall'])} | 应找到的省里，检索结果含证据的比例 |")
        w(f"| 检索 | 枚举题·上下文精确率 | {pct(e['ctx_precision'])} | 检索到的块里真正相关的比例 |")
    if by["fact"]:
        f = S["fact"]
        w(f"| 检索 | 事实题·MRR | {num(f['mrr'])} | 金标块排名倒数的均值，1 为每次都排第一 |")
        w(f"| 检索 | 事实题·Hit@1 / @3 / @5 | {pct(f['hit1'])} / {pct(f['hit3'])} / {pct(f['hit5'])} | 金标块排进前 k 的比例 |")
        w(f"| 检索 | 事实题·平均返回块数 | {num(f['n_ret'], 1)} | 单省配额 30，大于多数省份的总块数 |")
    if by["compare"]:
        w(f"| 检索 | 对比题·两省金标都检索到 | {pct(S['cmp']['both'])} | |")
    if by["aggregate"]:
        w(f"| 检索 | 汇总题·检索到金标的省份比例 | {pct(S['agg']['ret'])} | |")
    if by["enumerate"]:
        w(f"| 答案 | 枚举题·完整率 | {pct(S['enum']['ans_recall'])} | 应列出的省里，答案给出（或看得到证据）的比例 |")
        if S["enum"]["ans_precision"] is not None:
            w(f"| 答案 | 枚举题·精确率 | {pct(S['enum']['ans_precision'])} | 答案点名的省里，真正提到的比例 |")
    if by["fact"]:
        w(f"| 答案 | 事实题·正确率 | {pct(S['fact']['acc'])} | 答案给出了正确的 2025 年目标 |")
    if by["compare"]:
        w(f"| 答案 | 对比题·完整率 | {pct(S['cmp']['acc'])} | 两省目标各算一个信息点 |")
    if by["aggregate"]:
        w(f"| 答案 | 汇总题·完整率 | {pct(S['agg']['acc'])} | 31 省目标各算一个信息点 |")
    if by["negative"]:
        neg = "不适用（摘编模式无法拒答）" if S["neg"] is None else pct(S["neg"])
        w(f"| 答案 | 无答案题·正确拒答率 | {neg} | 资料里没有时，是否明确说没有 |")
    w(f"| 体验 | 时延 P50 / P90 | {num(S['p50'])}s / {num(S['p90'])}s | 单次查询耗时 |")

    w("\n## 二、信息点级归因（检索 × 答案）\n")
    w("每个信息点（枚举题的每个省、事实/对比/汇总题的每个目标）按「检索到没有 × 答出没有」归类：\n")
    w("| 题型 | 信息点 | ✅ 检索到且答出 | ⚠️ 检索到但没答出（生成层） | ❌ 没检索到（检索层） | ❓ 答出但没检索到 | 检索状态未知 |")
    w("|---|---|---|---|---|---|---|")
    tot = Counter()
    for t in TYPE_LABEL:
        c = A.get(t)
        if not c:
            continue
        tot.update(c)
        n = sum(c.values())
        unk = c["unknown_ok"] + c["unknown_miss"]
        w(f"| {TYPE_LABEL[t]} | {n} | {c['ok']} | {c['gen_loss']} | {c['ret_loss']} | {c['no_ret_but_ok']} | {unk} |")
    n = sum(tot.values())
    if n:
        unk = tot["unknown_ok"] + tot["unknown_miss"]
        w(f"| **合计** | **{n}** | **{tot['ok']}** | **{tot['gen_loss']}** | **{tot['ret_loss']}** | **{tot['no_ret_but_ok']}** | **{unk}** |")
        lost = tot["gen_loss"] + tot["ret_loss"]
        if lost:
            g = tot["gen_loss"] / lost
            if g >= 0.6:
                w(f"\n**结论：主要损失在生成层**——没答出的信息点里 {pct(g)} 其实已经检索到了。"
                  "优先改答案生成环节，加大检索量解决不了这个问题。")
            elif g <= 0.4:
                w(f"\n**结论：主要损失在检索层**——没答出的信息点里 {pct(1 - g)} 根本没被检索到。优先改检索。")
            else:
                w(f"\n**结论：两层都有明显损失**（生成层 {pct(g)}，检索层 {pct(1 - g)}），需要分别处理。")
        if tot["no_ret_but_ok"]:
            w(f"\n注意：有 {tot['no_ret_but_ok']} 个信息点「答出但没检索到」——可能来自模型先验知识，也可能是碰巧蒙对，需人工核查。")

    bad_intent = [r for r in recs if not r["intent_ok"]]
    if bad_intent:
        w("\n## 三、路由错误\n")
        w("| 题目 | 实际路由 | 应为 |")
        w("|---|---|---|")
        for r in bad_intent:
            w(f"| {r['question']} | {r['query_type']} | {' / '.join(r['expected_types'])} |")

    w("\n## 四、分题型明细\n")
    if by["enumerate"]:
        w("### 枚举题\n")
        w("| ID | 问题 | 应有省数 | 检索·省份召回 | 上下文精确率 | 答案·完整率 |")
        w("|---|---|---|---|---|---|")
        for r in by["enumerate"]:
            n_gt = len(r["units"])
            w(f"| {r['id']} | {r['question']} | {n_gt} | {pct(r['ret'].get('prov_recall'))} | "
              f"{pct(r['ret'].get('ctx_precision'))} | {pct(r['ans'].get('recall'))} |")
    for t in ("fact", "compare", "aggregate"):
        if by[t]:
            w(f"\n### {TYPE_LABEL[t]}\n")
            w("| ID | 问题 | 答对 | 诊断 |")
            w("|---|---|---|---|")
            for r in by[t]:
                w(f"| {r['id']} | {r['question']} | {pct(r['ans']['correct'])} | {r['diag']} |")
    if by["negative"]:
        w("\n### 无答案题\n")
        w("| ID | 问题 | 结果 |")
        w("|---|---|---|")
        for r in by["negative"]:
            ok = r["ans"].get("refusal_ok")
            w(f"| {r['id']} | {r['question']} | {'—' if ok is None else ('✓ ' if ok else '✗ ') + r['diag']} |")

    worst = sorted((r for r in recs if r["score"] is not None), key=lambda r: (r["score"], r["id"]))[:12]
    if worst:
        w("\n## 五、坏例清单（得分最低的 12 题）\n")
        for r in worst:
            w(f"- **[{r['id']}] {r['question']}** — 得分 {pct(r['score'])}。{r['diag']}")

    return "\n".join(L) + "\n"


# ====================================================================== 入口


def main():
    ap = argparse.ArgumentParser(description="RAG 评测")
    ap.add_argument("--api", help="被测服务地址，如 http://127.0.0.1:8000；不填则进程内评测 Demo 后端")
    ap.add_argument("--types", help="只跑这些题型，逗号分隔：enumerate,fact,compare,aggregate,negative")
    ap.add_argument("--out", help="报告另存为 Markdown 文件")
    ap.add_argument("--dump", help="逐题明细另存为 JSONL")
    args = ap.parse_args()

    items = [json.loads(line) for line in open(EVAL_SET, encoding="utf-8") if line.strip()]
    if args.types:
        keep = set(args.types.split(","))
        items = [it for it in items if it["type"] in keep]

    backend = ApiBackend(args.api) if args.api else DemoBackend()
    print(f"▶ {backend.label}：评测 {len(items)} 题 …", file=sys.stderr)

    recs = []
    for i, it in enumerate(items, 1):
        recs.append(score(it, backend.ask(it["question"])))
        if i % 10 == 0 or i == len(items):
            print(f"  {i}/{len(items)}", file=sys.stderr)

    modes = {r["llm"] for r in recs}
    answer_mode = ("LLM 答案 · 启发式规则判分（需人工抽检校准）" if modes == {True}
                   else "摘编答案 · 判「答案里看不看得到证据」" if modes == {False}
                   else "混合（部分题 LLM 调用失败降级为摘编）")
    report = render(recs, backend.label, answer_mode)
    print(report)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"📄 报告已保存：{args.out}", file=sys.stderr)
    if args.dump:
        Path(args.dump).parent.mkdir(parents=True, exist_ok=True)
        with open(args.dump, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"📄 逐题明细已保存：{args.dump}", file=sys.stderr)


if __name__ == "__main__":
    main()
