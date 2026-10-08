from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class QueryOptions(BaseModel):
    output_format: Optional[str] = "province_list"  # 可选: province_list, detailed, comparison, statistics
    max_results: Optional[int] = 50
    include_stats: Optional[bool] = True

class QueryRequest(BaseModel):
    query: str
    options: Optional[QueryOptions] = None

class SourceChunk(BaseModel):
    id: str
    province: str
    chunk_type: str
    score: Optional[float] = None
    char_count: int
    excerpt: str

class QueryResponseData(BaseModel):
    content: str
    provinces: List[str]
    query_type: str
    output_format: str
    processing_time: float
    processing_stats: Optional[Dict[str, Any]] = None
    sources: Optional[List[SourceChunk]] = None

class QueryResponse(BaseModel):
    success: bool
    data: Optional[QueryResponseData] = None
    message: Optional[str] = None
    error: Optional[str] = None

class StatusResponseData(BaseModel):
    is_ready: bool
    vector_store_built: bool
    api_available: bool
    vector_stats: Optional[Dict[str, Any]] = None

class StatusResponse(BaseModel):
    success: bool
    data: Optional[StatusResponseData] = None
    message: Optional[str] = None
    error: Optional[str] = None

class SetupRequest(BaseModel):
    force_rebuild: Optional[bool] = False

class HealthResponse(BaseModel):
    status: str = "ok" 