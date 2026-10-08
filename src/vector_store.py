#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
向量存储管理器
负责文档向量化、存储和检索
"""

import os
import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
import faiss
from tqdm import tqdm

from data_processor import DocumentChunk
from embedding_manager import get_embedding_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorStore:
    """向量存储管理器"""
    
    def __init__(self, store_path: str, embedding_dim: int = 1024):
        """
        初始化向量存储
        
        Args:
            store_path: 存储路径
            embedding_dim: 向量维度
        """
        self.store_path = Path(store_path)
        self.embedding_dim = embedding_dim
        
        # FAISS索引
        self.index = None
        self.chunks = []  # 存储文档块信息
        self.chunk_embeddings = None
        
        # 文件路径
        self.index_file = self.store_path / "faiss_index.bin"
        self.chunks_file = self.store_path / "chunks_metadata.pkl"
        self.embeddings_file = self.store_path / "embeddings.npy"
        
        # 确保目录存在
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🗄️ 向量存储初始化")
        logger.info(f"📁 存储路径: {self.store_path}")
        logger.info(f"📐 向量维度: {embedding_dim}")
    
    def _create_faiss_index(self, dimension: int) -> faiss.Index:
        """
        创建FAISS索引
        
        Args:
            dimension: 向量维度
            
        Returns:
            faiss.Index: FAISS索引
        """
        # 使用L2距离的平面索引（适合中小规模数据）
        index = faiss.IndexFlatL2(dimension)
        
        # 如果数据量大，可以使用IVF索引
        # nlist = 100  # 聚类中心数量
        # quantizer = faiss.IndexFlatL2(dimension)
        # index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
        
        logger.info(f"📊 创建FAISS索引: {type(index).__name__}")
        return index
    
    def build_index(self, chunks: List[DocumentChunk], batch_size: int = 32, embedding_manager=None) -> bool:
        """
        构建向量索引
        
        Args:
            chunks: 文档块列表
            batch_size: 批处理大小
            embedding_manager: embedding管理器实例（可选）
            
        Returns:
            bool: 是否构建成功
        """
        logger.info(f"🔨 开始构建向量索引...")
        logger.info(f"📚 文档块数量: {len(chunks)}")
        
        if not chunks:
            logger.error("❌ 没有文档块可以索引")
            return False
        
        try:
            # 获取embedding管理器 - 使用SDPA优化
            if embedding_manager is None:
                embedding_manager = get_embedding_manager(attn_implementation="sdpa")
            
            if not embedding_manager.is_model_loaded():
                logger.error("❌ Embedding模型未加载")
                return False
            
            # 提取文本内容
            texts = [chunk.content for chunk in chunks]
            
            # 批量编码文本
            logger.info("🔄 正在编码文本...")
            embeddings = embedding_manager.encode_texts(
                texts, 
                batch_size=batch_size, 
                show_progress=True
            )
            
            if len(embeddings) == 0:
                logger.error("❌ 文本编码失败")
                return False
            
            # 更新向量维度
            self.embedding_dim = embeddings.shape[1]
            logger.info(f"📐 实际向量维度: {self.embedding_dim}")
            
            # 创建FAISS索引
            self.index = self._create_faiss_index(self.embedding_dim)
            
            # 添加向量到索引
            logger.info("📊 添加向量到索引...")
            self.index.add(embeddings.astype(np.float32))
            
            # 保存数据
            self.chunks = chunks
            self.chunk_embeddings = embeddings
            
            logger.info(f"✅ 向量索引构建完成!")
            logger.info(f"📊 索引大小: {self.index.ntotal}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 构建索引失败: {str(e)}")
            return False
    
    def save_index(self) -> bool:
        """
        保存索引到磁盘
        
        Returns:
            bool: 是否保存成功
        """
        try:
            if self.index is None:
                logger.error("❌ 没有可保存的索引")
                return False
            
            logger.info("💾 保存向量索引...")
            
            # 保存FAISS索引
            faiss.write_index(self.index, str(self.index_file))
            
            # 保存文档块元数据
            with open(self.chunks_file, 'wb') as f:
                pickle.dump(self.chunks, f)
            
            # 保存embeddings
            if self.chunk_embeddings is not None:
                np.save(self.embeddings_file, self.chunk_embeddings)
            
            logger.info(f"✅ 索引保存成功!")
            logger.info(f"📄 索引文件: {self.index_file}")
            logger.info(f"📄 元数据文件: {self.chunks_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存索引失败: {str(e)}")
            return False
    
    def load_index(self) -> bool:
        """
        从磁盘加载索引
        
        Returns:
            bool: 是否加载成功
        """
        try:
            if not self.index_file.exists():
                logger.warning(f"⚠️ 索引文件不存在: {self.index_file}")
                return False
            
            logger.info("📂 加载向量索引...")
            
            # 加载FAISS索引
            self.index = faiss.read_index(str(self.index_file))
            
            # 加载文档块元数据
            if self.chunks_file.exists():
                with open(self.chunks_file, 'rb') as f:
                    self.chunks = pickle.load(f)
            
            # 加载embeddings
            if self.embeddings_file.exists():
                self.chunk_embeddings = np.load(self.embeddings_file)
            
            # 更新维度信息
            if self.index:
                self.embedding_dim = self.index.d
            
            logger.info(f"✅ 索引加载成功!")
            logger.info(f"📊 索引大小: {self.index.ntotal}")
            logger.info(f"📚 文档块数量: {len(self.chunks)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载索引失败: {str(e)}")
            return False
    
    def search(self, query: str, top_k: int = 10, 
               province_filter: Optional[str] = None,
               chunk_type_filter: Optional[str] = None) -> List[Tuple[DocumentChunk, float]]:
        """
        搜索相关文档
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            province_filter: 省份过滤
            chunk_type_filter: 块类型过滤
            
        Returns:
            List[Tuple[DocumentChunk, float]]: (文档块, 相似度分数)列表
        """
        if self.index is None:
            logger.error("❌ 索引未加载")
            return []
        
        try:
            # 编码查询文本 - 使用SDPA优化
            # Jina v4 是非对称检索模型：查询侧必须用 query 前缀（encode_query），
            # 文档侧用 passage 前缀，两者不能混用
            embedding_manager = get_embedding_manager(attn_implementation="sdpa")
            query_embedding = embedding_manager.encode_query(query).reshape(1, -1)
            
            if len(query_embedding) == 0:
                logger.error("❌ 查询编码失败")
                return []
            
            # 搜索相似向量 - 支持大量检索
            search_k = min(max(top_k * 4, 200), self.index.ntotal)  # 至少搜索200个结果，最多4倍
            scores, indices = self.index.search(
                query_embedding.astype(np.float32), 
                search_k
            )
            
            results = []
            
            for score, idx in zip(scores[0], indices[0]):
                if idx >= len(self.chunks):
                    continue
                
                chunk = self.chunks[idx]
                
                # 应用过滤器
                if province_filter and chunk.province != province_filter:
                    continue
                
                if chunk_type_filter and chunk.chunk_type != chunk_type_filter:
                    continue
                
                # 转换距离为相似度分数 (L2距离转余弦相似度近似)
                similarity = 1.0 / (1.0 + score)
                
                results.append((chunk, similarity))
                
                if len(results) >= top_k:
                    break
            
            logger.debug(f"🔍 搜索完成: 查询='{query[:50]}...', 结果数={len(results)}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 搜索失败: {str(e)}")
            return []
    
    def get_chunks_by_province(self, province: str) -> List[DocumentChunk]:
        """
        获取指定省份的所有文档块
        
        Args:
            province: 省份名称
            
        Returns:
            List[DocumentChunk]: 文档块列表
        """
        return [chunk for chunk in self.chunks if chunk.province == province]
    
    def get_chunks_by_type(self, chunk_type: str) -> List[DocumentChunk]:
        """
        获取指定类型的所有文档块
        
        Args:
            chunk_type: 块类型
            
        Returns:
            List[DocumentChunk]: 文档块列表
        """
        return [chunk for chunk in self.chunks if chunk.chunk_type == chunk_type]
    
    def get_statistics(self) -> Dict:
        """
        获取索引统计信息
        
        Returns:
            Dict: 统计信息
        """
        if not self.chunks:
            return {}
        
        # 省份统计
        province_stats = {}
        type_stats = {}
        
        for chunk in self.chunks:
            # 省份统计
            province = chunk.province
            if province not in province_stats:
                province_stats[province] = {"count": 0, "total_chars": 0}
            province_stats[province]["count"] += 1
            province_stats[province]["total_chars"] += chunk.char_count
            
            # 类型统计
            chunk_type = chunk.chunk_type
            if chunk_type not in type_stats:
                type_stats[chunk_type] = 0
            type_stats[chunk_type] += 1
        
        return {
            "total_chunks": len(self.chunks),
            "total_provinces": len(province_stats),
            "index_size": self.index.ntotal if self.index else 0,
            "embedding_dimension": self.embedding_dim,
            "province_stats": province_stats,
            "type_stats": type_stats
        }
    
    def is_built(self) -> bool:
        """检查索引是否已构建"""
        return self.index is not None and self.index.ntotal > 0

# 全局向量存储实例
_vector_store = None

def get_vector_store() -> VectorStore:
    """获取全局向量存储实例 - 使用SDPA优化"""
    global _vector_store
    if _vector_store is None:
        from config.config import DATA_PATHS
        
        # 获取embedding维度 - 使用SDPA优化
        embedding_manager = get_embedding_manager(attn_implementation="sdpa")
        embedding_dim = embedding_manager.get_embedding_dimension()
        
        _vector_store = VectorStore(
            store_path=str(DATA_PATHS["vector_store"]),
            embedding_dim=embedding_dim
        )
        
        # 尝试加载已有索引
        _vector_store.load_index()
    
    return _vector_store

 