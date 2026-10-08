from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from API_KIT.api_models import QueryRequest, QueryResponse, StatusResponse, SetupRequest, HealthResponse
from typing import Optional
import sys
from pathlib import Path

# 添加项目根目录到路径，导入主系统
sys.path.append(str(Path(__file__).parent.parent))
from main import GovernmentReportRAG

app = FastAPI(title="政府工作报告RAG API", description="为AI前端和自动化工具提供标准化接口", version="1.0.0")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化RAG系统（单例）
rag_system = GovernmentReportRAG()

@app.post("/api/query", response_model=QueryResponse)
def query_api(request: QueryRequest):
    if not rag_system.is_ready:
        return QueryResponse(success=False, error="系统未就绪，请先初始化。")
    try:
        result = rag_system.query(request.query)
        if result["success"]:
            return QueryResponse(
                success=True,
                data={
                    "content": result["content"],
                    "provinces": result.get("provinces", []),
                    "query_type": result.get("query_type", "unknown"),
                    "output_format": result.get("output_format", "unknown"),
                    "processing_time": result.get("processing_time", 0),
                    "processing_stats": result.get("processing_stats", {}),
                    "sources": result.get("sources", [])
                },
                message="查询成功"
            )
        else:
            return QueryResponse(success=False, error=result.get("error", "查询失败"))
    except Exception as e:
        return QueryResponse(success=False, error=str(e))

@app.get("/api/status", response_model=StatusResponse)
def status_api():
    try:
        status = rag_system.get_system_status()
        return StatusResponse(success=True, data=status)
    except Exception as e:
        return StatusResponse(success=False, error=str(e))

@app.post("/api/setup", response_model=StatusResponse)
def setup_api(request: SetupRequest):
    try:
        ok = rag_system.setup_system(force_rebuild=request.force_rebuild)
        status = rag_system.get_system_status()
        return StatusResponse(success=ok, data=status)
    except Exception as e:
        return StatusResponse(success=False, error=str(e))

@app.get("/api/health", response_model=HealthResponse)
def health_api():
    return HealthResponse(status="ok") 