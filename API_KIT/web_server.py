#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一 Web 服务器：聊天前端 + RAG API，跨平台启动。

    python API_KIT/web_server.py            # 自动模式：真实系统可用则用，否则降级 demo
    python API_KIT/web_server.py --demo     # 强制 demo 模式（无 GPU / 无权重 / 无 Key）
    python API_KIT/web_server.py --port 8000

自动模式的降级规则：尝试初始化 main.GovernmentReportRAG（需要 config/config.py、
Jina 模型权重、已构建的向量索引），任一环节失败即回退到 DemoRAG
（TF-IDF + mvp/chunks.json），前端顶栏会标明当前运行模式。

不修改、不影响现有的 API_KIT/api_server.py。
"""
import sys
import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("web_server")

WEB_DIR = ROOT / "web"


def build_backend(force_demo: bool):
    """返回 (rag, mode)。真实系统初始化失败时自动降级 demo。"""
    if not force_demo:
        try:
            from main import GovernmentReportRAG
            rag = GovernmentReportRAG()
            if not rag.is_ready:
                if not rag.setup_system():
                    raise RuntimeError("setup_system() 返回 False（索引未构建或模型缺失）")
            logger.info("✅ 完整系统初始化成功")
            return rag, "full"
        except Exception as e:
            logger.warning(f"完整系统不可用（{e}），降级为 demo 模式")
    from API_KIT.demo_rag import DemoRAG
    return DemoRAG(), "demo"


class QueryIn(BaseModel):
    query: str


def create_app(force_demo: bool = False) -> FastAPI:
    rag, mode = build_backend(force_demo)

    app = FastAPI(title="政府工作报告 RAG · 问答前端", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.post("/api/query")
    def query_api(body: QueryIn):
        q = body.query.strip()
        if not q:
            return {"success": False, "error": "查询不能为空"}
        result = rag.query(q)
        result.setdefault("mode", mode)
        result.setdefault("sources", [])
        return result

    @app.get("/api/status")
    def status_api():
        status = rag.get_system_status()
        status["mode"] = mode
        return {"success": True, "data": status}

    @app.get("/api/health")
    def health_api():
        return {"status": "ok", "mode": mode}

    return app


def main():
    parser = argparse.ArgumentParser(description="RAG 聊天前端服务器")
    parser.add_argument("--demo", action="store_true", help="强制 demo 模式")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn
    app = create_app(force_demo=args.demo)
    logger.info(f"🌐 打开 http://{args.host}:{args.port} 开始对话")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
