#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Demo 模式 RAG 后端：无 GPU、无模型权重、无 API Key 也能跑。

检索复用 mvp/step2_retrieval.py 的 MiniStore（TF-IDF 字符 n-gram，
pre-filter 版检索），数据用仓库自带的 mvp/chunks.json（855 块 / 31 省）。

生成两档：
- 配置了 SILICONFLOW_API_KEY 环境变量 → 调硅基流动 LLM 生成答案
- 未配置 → 摘编模式，按省分组返回检索到的原文片段

返回契约与 main.py:130 GovernmentReportRAG.query() 保持一致，
额外多一个 sources 字段（引用来源，前端展示用）。
"""
import os
import re
import sys
import time
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mvp"))

from step2_retrieval import MiniStore, PROVINCES  # noqa: E402

logger = logging.getLogger(__name__)

# 与 config.example.py RETRIEVAL_CONFIG 对齐的每省块数配额
BUDGETS = {
    "single_province": 30,
    "multi_province": 15,
    "all_provinces": 8,
    "comparison": 25,
    "statistics": 8,
    "general": 10,
}
COMPARISON_TOTAL_CAP = 150
MAX_SOURCES = 12          # 前端引用面板最多展示的块数
EXCERPT_LEN = 300         # 引用卡片摘要长度

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("SILICONFLOW_MODEL", "Tongyi-Zhiwen/QwenLong-L1-32B")


class DemoRAG:
    """与 GovernmentReportRAG 同契约的轻量后端。"""

    def __init__(self, chunks_path: Path = ROOT / "mvp" / "chunks.json"):
        with open(chunks_path, encoding="utf-8") as f:
            self.chunks = json.load(f)
        self.store = MiniStore(self.chunks)
        self.api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
        self.is_ready = True
        logger.info(f"DemoRAG 就绪: {len(self.chunks)} 块 / "
                    f"{len(set(c['province'] for c in self.chunks))} 省, "
                    f"LLM {'可用' if self.api_key else '未配置(摘编模式)'}")

    # ------------------------------------------------------------------ 意图

    def analyze_intent(self, query: str) -> dict:
        mentioned = [p for p in PROVINCES if p in query]
        cmp_kw = any(k in query for k in ["对比", "比较", "差异", "区别", "异同"])
        all_kw = any(k in query for k in ["所有省份", "全部省份", "各省", "31省",
                                          "全国", "哪些省", "哪几个省"])
        stat_kw = any(k in query for k in ["统计", "汇总", "总计"])

        if len(mentioned) >= 2 and cmp_kw:
            qtype, fmt = "comparison", "comparison"
        elif len(mentioned) == 1:
            qtype, fmt = "single_province", "detailed"
        elif len(mentioned) >= 2:
            qtype, fmt = "multi_province", "detailed"
        elif all_kw:
            qtype, fmt = "all_provinces", "province_list"
        elif stat_kw:
            qtype, fmt = "statistics", "statistics"
        else:
            qtype, fmt = "general", "detailed"
        return {"type": qtype, "provinces": mentioned, "output_format": fmt}

    # ------------------------------------------------------------------ 检索

    def retrieve(self, user_query: str):
        """公开检索入口：返回 (intent, [(chunk, score), ...])，按分数降序。

        与 query() 走同一条检索路径，评测脚本用它拿到完整检索结果
        （query() 返回的 sources 只截取前 MAX_SOURCES 条）。
        """
        intent = self.analyze_intent(user_query)
        return intent, self._retrieve(user_query, intent)

    def _retrieve(self, query: str, intent: dict):
        """返回 [(chunk, score)]，按 pre-filter 逐省检索。"""
        qtype = intent["type"]
        per_k = BUDGETS[qtype]
        targets = intent["provinces"] or (
            PROVINCES if qtype in ("all_provinces", "statistics") else None)

        if targets:
            results = []
            for p in targets:
                results.extend(self.store.search_prefilter(query, per_k, p))
            if qtype == "comparison":
                results = sorted(results, key=lambda t: -t[1])[:COMPARISON_TOTAL_CAP]
        else:
            results = self.store.search_prefilter(query, per_k * 6)
        return sorted(results, key=lambda t: -t[1])

    # ------------------------------------------------------------------ 生成

    def _digest(self, query: str, results, intent: dict) -> str:
        """摘编模式：无 LLM 时按省分组返回原文片段。"""
        by_prov = {}
        for c, s in results:
            by_prov.setdefault(c["province"], []).append((c, s))

        lines = ["> ⚠️ 未配置 LLM API Key，以下为检索到的报告原文摘编"
                 "（配置 `SILICONFLOW_API_KEY` 环境变量后可生成完整答案）。\n"]
        wide = intent["type"] in ("all_provinces", "statistics", "comparison")
        n_chunk = 1 if wide else 3
        n_char = 160 if wide else 450

        for prov in sorted(by_prov, key=lambda p: -by_prov[p][0][1]):
            lines.append(f"### {prov}")
            for c, s in by_prov[prov][:n_chunk]:
                text = re.sub(r"\s+", " ", c["content"])[:n_char]
                lines.append(f"- {text}…  *(块 {c['id']}，相关度 {s:.3f})*")
            lines.append("")
        return "\n".join(lines)

    def _generate_llm(self, query: str, results, intent: dict):
        """有 Key 时调硅基流动生成（请求结构与 src/api_client.py 一致）。"""
        import requests

        parts, used = [], 0
        for c, s in results:
            if used + c["char_count"] > 40000:
                break
            parts.append(f"【{c['province']}】{c['content']}")
            used += c["char_count"]
        context = "\n\n".join(parts)

        prompt = (
            "你是政府工作报告分析助手。请严格根据下面的参考资料回答用户问题，"
            "所有数字必须来自资料原文，资料中没有的信息明确说明未找到，不要编造。\n\n"
            f"【用户问题】{query}\n\n【参考资料】\n{context}\n\n"
            "请用 Markdown 格式回答，涉及多省时用表格或分省小节呈现。"
        )
        resp = requests.post(
            SILICONFLOW_URL,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": DEFAULT_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.3, "max_tokens": 8192, "stream": False},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------ 主入口

    def query(self, user_query: str) -> dict:
        start = time.time()
        try:
            intent, results = self.retrieve(user_query)

            llm_used = False
            if self.api_key:
                try:
                    content = self._generate_llm(user_query, results, intent)
                    llm_used = True
                except Exception as e:
                    logger.warning(f"LLM 调用失败，降级为摘编模式: {e}")
                    content = self._digest(user_query, results, intent)
            else:
                content = self._digest(user_query, results, intent)

            provinces, seen = [], set()
            for c, _ in results:
                if c["province"] not in seen:
                    seen.add(c["province"])
                    provinces.append(c["province"])

            sources = [{
                "id": c["id"],
                "province": c["province"],
                "chunk_type": c["chunk_type"],
                "score": round(s, 4),
                "char_count": c["char_count"],
                "excerpt": re.sub(r"\s+", " ", c["content"])[:EXCERPT_LEN],
            } for c, s in results[:MAX_SOURCES]]

            return {
                "success": True,
                "content": content,
                "provinces": provinces,
                "query_type": intent["type"],
                "output_format": intent["output_format"],
                "processing_time": time.time() - start,
                "processing_stats": {"success_rate": 1.0,
                                     "total_batches": 1,
                                     "successful_batches": 1},
                "query_plan": {"strategy": f"demo_{intent['type']}", "batches": 1},
                "sources": sources,
                "mode": "demo",
                "llm_used": llm_used,
            }
        except Exception as e:
            logger.exception("DemoRAG 查询失败")
            return {"success": False, "error": str(e), "content": "",
                    "processing_time": time.time() - start}

    def get_system_status(self) -> dict:
        return {
            "is_ready": True,
            "vector_store_built": True,
            "api_available": bool(self.api_key),
            "mode": "demo",
            "vector_stats": {
                "total_chunks": len(self.chunks),
                "total_provinces": len(set(c["province"] for c in self.chunks)),
                "retrieval": "TF-IDF char 2-3gram (pre-filter)",
            },
        }
