# 技术说明文档

政府工作报告 RAG 系统 —— 逐层拆解技术栈、数据流与关键实现。

> 本文所有技术论断都标注了 `文件:行号`。引用的数字均为在真实语料上的实测值(见 `mvp/`),不使用 README 中的宣传口径。
> 第 1~9 节为中立技术描述;已知问题集中在 [第 10 节](#10-已知问题与改进优先级)。

---

## 目录

1. [项目定位与解决的问题](#1-项目定位与解决的问题)
2. [技术栈总览](#2-技术栈总览)
3. [离线建库链路](#3-离线建库链路)
4. [在线查询链路](#4-在线查询链路)
5. [结果聚合层](#5-结果聚合层)
6. [API 服务层](#6-api-服务层)
7. [配置体系全量说明](#7-配置体系全量说明)
8. [部署形态与硬件要求](#8-部署形态与硬件要求)
9. [技术选型的理由与权衡](#9-技术选型的理由与权衡)
10. [已知问题与改进优先级](#10-已知问题与改进优先级)

---

## 1. 项目定位与解决的问题

### 1.1 数据规模

| 项 | 实测值 |
|---|---|
| 文档数 | 31 份(31 个省级行政区,不含港澳台) |
| 单份字数 | 约 1.3 万字(河南 12,975 字) |
| 总字数 | 约 60 万字 |
| 切块后 | **855 个块** |
| 各省块数 | 最少 16(吉林)、中位 28、最多 50、平均 27.6 |
| 文档格式 | `.docx`,存于 `docs/31省区市政府工作报告.zip` |

### 1.2 解决的问题

核心痛点是**跨文档的横向检索**。回答"哪些省把低空经济写进了 2025 年重点任务"需要通读 31 份文档——人工耗时 2~4 小时,且容易漏。

实测语料中,29/31 个省都提到了"低空经济",这类跨省专题问题的人工成本正是系统的价值来源。

### 1.3 RAG 在此处的作用边界

系统承诺:一句自然语言提问 → 1 分钟内给出答案 → 每个数字都来自原文。

需要注意规模与方案的匹配关系:

| 查询范围 | 涉及字数 | 是否需要检索 |
|---|---|---|
| 单省 | 约 1.3 万字 | 长上下文模型可直接容纳 |
| 2~5 省 | 约 6 万字 | 长上下文模型仍可容纳 |
| 全 31 省 | 约 60 万字 | **必须先检索筛选** |

---

## 2. 技术栈总览

### 2.1 分层清单

| 层 | 技术 | 版本约束 | 使用位置 |
|---|---|---|---|
| **文档解析** | python-docx | `==0.8.11` | `data_processor.py:17` |
| **向量模型** | jinaai/jina-embeddings-v4 | 本地权重 | `config.example.py:26` |
| | transformers(`AutoModel`) | `>=4.52.0` | `embedding_manager.py:16` |
| | torch(`bfloat16` / SDPA) | `>=2.5.0` | `embedding_manager.py:14` |
| | peft | `>=0.15.2` | Jina v4 官方依赖链,由 remote code 运行时使用 |
| | torchvision / pillow | 无约束 | 同上(Jina v4 为多模态模型) |
| **向量库** | faiss-cpu(`IndexFlatL2`) | `==1.7.4` | `vector_store.py:14,66` |
| | numpy | `==1.24.3` | `vector_store.py:10` |
| **相似度** | scikit-learn(`cosine_similarity`) | `==1.3.2` | `embedding_manager.py:339` |
| **生成模型** | Tongyi-Zhiwen/QwenLong-L1-32B | 硅基流动托管 | `config.example.py:18` |
| **HTTP 客户端** | requests(`Session`) | `==2.31.0` | `api_client.py:8,43` |
| **API 服务** | FastAPI / uvicorn / pydantic | **均不锁版本** | `API_KIT/requirements_api.txt` |
| **内网穿透** | ngrok v3(Windows amd64 二进制) | — | `API_KIT/start_ngrok.bat:8` |
| **进度显示** | tqdm | `==4.66.1` | `embedding_manager.py:15` |

### 2.2 值得单独说明的三件事

**① LLM 调用不走 SDK。** 尽管 `requirements.txt:12` 装了 `openai==1.3.8`,且硅基流动提供的是 OpenAI 兼容接口(`base_url` 以 `/v1` 结尾),`api_client.py` 全程用 `requests` 手写 REST 调用(`api_client.py:8`),手拼 payload、手解 `result["choices"][0]["message"]["content"]`(`api_client.py:111`)。全仓库零 `import openai`。

**② 存在两套并行的 Embedding 实现。**

| | `embedding_manager.py` | `embedding_manager_st.py` |
|---|---|---|
| 底层 | `transformers.AutoModel` + `model.encode_text()` | `sentence_transformers.SentenceTransformer` + `model.encode()` |
| 主链路引用 | ✅ `vector_store.py:18` | ❌ 全仓库零引用 |
| 离线保护 | 强制离线(环境变量 + `local_files_only`) | 无,本地缺失会转为在线下载 |
| attention 降级 | 三级降级链 | 无,失败即 `raise` |
| 精度 | 显式 `bfloat16` + `eval()` + `no_grad()` | 交由 ST 内部处理 |

两者接口不兼容,无法直接替换:主链路依赖 `is_model_loaded()`(`vector_store.py:100`)与 `get_embedding_dimension()`(`vector_store.py:360`),ST 版都没有。

**③ 版本锁定策略不统一。** 核心工具链用 `==` 精确锁,模型相关用 `>=` 下限,`torchvision`/`pillow` 完全不写约束。`flash-attn>=2.0.0` 在 `requirements.txt:22` 被注释禁用,理由写在第 21 行:Windows 下编译困难,直接用 PyTorch 2.x 的 `attn_implementation="sdpa"` 更简单且加速明显。

---

## 3. 离线建库链路

```
docs/*.docx
   ├─[3.1]→ python-docx 解析成纯文本
   ├─[3.2]→ 切块 + 省份标注 → List[DocumentChunk] → data/processed/
   ├─[3.3]→ Jina v4 编码 → np.ndarray (N, D)
   └─[3.4]→ FAISS IndexFlatL2 → data/vectors/(3 个文件)
```

这条链路只跑一次,产物落盘复用。入口在 `main.py:69`(`setup_system`)与独立脚本 `rebuild_index.py`。

### 3.1 文档解析

`data_processor.py:151-160`,`GovernmentReportProcessor.read_docx_file`:

```python
doc = Document(file_path)
paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
content = "\n".join(paragraphs)
```

只取 `doc.paragraphs`,跳过空段。**不处理表格**(`doc.tables`)、页眉页脚、批注。元数据记录 `filename` / `file_size` / `paragraph_count` / `char_count`(`data_processor.py:163-168`)。

实测河南那份解析出 75 个段落、12,975 字。

### 3.2 切块与元数据标注

**切块算法**(`data_processor.py:205-293`,`split_text_into_chunks`)是段落级聚合而非字符级硬切:

1. 按 `\n` 拆成段落
2. 逐段累加进 `current_chunk`
3. 当 `len(current_chunk) + len(paragraph) > chunk_size` 且当前块非空时,封块
4. 新块以上一块末尾 `chunk_overlap` 个字符开头(`data_processor.py:257-259`)

参数来自 `DOCUMENT_CONFIG`:`chunk_size=1000`、`chunk_overlap=200`(20% 重叠)。

因为是段落级聚合,实际块长有浮动——实测**最短 303 字、中位 874、最长 1543**。

**`DocumentChunk` 数据结构**(`data_processor.py:25-41`,`@dataclass`):

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | `f"{province}_{chunk_id:03d}"`,如 `河南_003` |
| `province` | str | 省份,**按省检索的依据** |
| `content` | str | 正文 |
| `chunk_type` | str | `title` / `content` / `target` / `summary` |
| `metadata` | Dict | 文档元数据 + `chunk_index` |
| `char_count` | int | 字符数 |
| `source` | str | 源文件名 |
| `start_pos` / `end_pos` | int | 位置偏移 |
| `chunk_id` | int | 块序号,相邻块聚合的依据 |

**省份识别是两级策略**(`data_processor.py:315-321`):

1. 优先从**文件名**提取(`extract_province_from_filename`,`data_processor.py:105`)
2. 失败则从**正文前 1000 字**提取(`extract_province_from_content`,`data_processor.py:121`)
3. 都失败标记为 `"未知"`

匹配用的是 `province_patterns`(`data_processor.py:60-92`),每个省配全称与简称,如 `"北京": ["北京", "京"]`。

**`chunk_type` 判定规则**(`data_processor.py:178-203`,按优先级):

```python
if 任一 target_keywords 命中:              return "target"   # 16 个词
if len(text) < 100 and 含中文数字一~十:     return "title"
if "摘要"/"概述"/"总体" in text:            return "summary"
return "content"
```

实测分布:`target` 476 块(55.7%)、`content` 333 块(38.9%)、`summary` 46 块(5.4%)、`title` **0 块**。

**落盘**(`data_processor.py:374-437`):`processed_chunks.json`(全部块的 JSON)+ `processing_stats.json`(按省/按类型统计)。

### 3.3 向量模型加载

`embedding_manager.py:70-175`,`JinaEmbeddingManager.download_and_load_model`。函数名带 download,实际**完全禁网**。

**加载流程:**

```
① 设进程级离线环境变量                    :82-83
     TRANSFORMERS_OFFLINE=1 / HF_HUB_OFFLINE=1
② 删除 FLASH_ATTENTION_FORCE_DISABLE      :86-87
③ 校验本地目录存在                        :90-93
④ 校验 config.json 存在                   :95-98
⑤ AutoModel.from_pretrained(按降级链)     :104-159
⑥ model.to(device) + model.eval()         :162-163
```

`from_pretrained` 的固定参数:

| 参数 | 值 | 行号 |
|---|---|---|
| `trust_remote_code` | `True`(硬编码) | 106,124,137,150 |
| `torch_dtype` | `torch.bfloat16`(硬编码) | 109,127,140,153 |
| `local_files_only` | `True` | 108,126,139,151 |

`trust_remote_code=True` 是必须的:Jina v4 的编码逻辑在模型仓库自带的远端代码里,`encode_text()` 方法也来自那里,通用 `AutoModel` 靠它才能识别该架构。因此本文件不 import 任何 Tokenizer/Processor。

**attention 三级降级链**(`embedding_manager.py:104-159`):

```
首选 flash_attention_2  →  失败降 sdpa  →  再失败降 eager     (:119-143)
首选 sdpa               →  失败降 eager                        (:146-156)
首选其他值              →  直接 raise                          (:158-159)
```

每次降级都回写 `self.attn_implementation`(`:129,142,155`)。默认值是 `"sdpa"`(`:31`)。

**设备选择**(`embedding_manager.py:53-56`):`device=None` 时按 `torch.cuda.is_available()` 自动选,不读配置。

**编码**(`embedding_manager.py:177-251`,`encode_texts`):

```python
def encode_texts(self, texts, task="retrieval", prompt_name="passage",
                 batch_size=32, show_progress=True):
    ...
    with torch.no_grad():                                    # :210
        for batch in tqdm(batches, ...):                     # :211
            batch_embeddings = self.model.encode_text(        # :214
                texts=batch, task=task, prompt_name=prompt_name)
    return np.vstack(numpy_embeddings)                       # :247
```

`task` 与 `prompt_name` 是 Jina v4 的两个语义开关:

- `task`:`"retrieval"` / `"text-matching"` / `"code"`
- `prompt_name`:`"query"` / `"passage"` —— **非对称检索模型的前缀区分**,查询与文档使用不同前缀

三个上层入口:

| 方法 | 行号 | task | prompt_name |
|---|---|---|---|
| `encode_query` | 253 | `retrieval` | `query` |
| `encode_passages` | 267 | `retrieval` | `passage` |
| `encode_for_matching` | 289 | `text-matching` | (未传,沿用默认 `passage`) |

**维度探测**(`embedding_manager.py:310-324`):不读配置也不读 `model.config.hidden_size`,而是用字符串 `"test"` 跑一次真实前向推理,取 `shape[1]`。无缓存。

### 3.4 向量索引

`vector_store.py`,`VectorStore` 类。

**索引类型**(`vector_store.py:55-74`):

```python
index = faiss.IndexFlatL2(dimension)      # :66
# 大数据量可换 IVF —— 已写成注释保留   :68-71
```

`IndexFlatL2` 是暴力精确检索,不做聚类近似。**没有调用 `faiss.normalize_L2`**,入库向量是模型原始输出,未做 L2 归一化。

**构建**(`vector_store.py:76-141`,`build_index`):

```
提取 chunk.content 列表           :105
批量编码(batch_size=32)          :109-113
读实际维度 embeddings.shape[1]     :120
建索引并 add(float32)             :124-128
```

维度是从编码结果实测得来,而非配置声明。

**落盘三文件**(`vector_store.py:143-176`,`save_index`):

| 文件 | 格式 | 内容 |
|---|---|---|
| `faiss_index.bin` | `faiss.write_index` | 向量索引 |
| `chunks_metadata.pkl` | `pickle.dump` | `List[DocumentChunk]` 全部元数据 |
| `embeddings.npy` | `np.save` | 原始向量矩阵 |

路径来自 `DATA_PATHS["vector_store"]`(默认 `data/vectors/`)。

---

## 4. 在线查询链路

```
用户 query
   ├─[4.1]→ query_router: 意图识别 → QueryPlan(批次策略 + 批次列表)
   ├─[4.2]→ retriever: 五路分层检索 → RetrievalResult
   ├─[4.3]→ 截断 + format_context → context 字符串
   ├─[4.4]→ _build_prompt → 完整 prompt
   ├─[4.5]→ api_client → QwenLong-L1-32B → 回答文本
   └─[ 5 ]→ result_aggregator(仅多批次时)
```

编排入口 `main.py:130-220`(`GovernmentReportRAG.query`)。

### 4.1 意图识别与 QueryPlan

**`QueryPlan`**(`query_router.py:21-28`,`@dataclass`):`query_type` / `batch_strategy` / `batches` / `expected_provinces` / `output_format`。

**意图识别**(`query_router.py:207-249`,`_identify_intent`)是纯中文关键词子串匹配,无正则、无分词、无模型:

```python
if any(kw in query for kw in ["所有省份","各省","31省","全国"]):  all_provinces   # :218
elif len(mentioned_provinces) == 1:                              single_province # :220
elif len(mentioned_provinces) > 1:                               multi_province  # :222
elif any(kw in query for kw in ["对比","比较"]):                  comparison      # :224
elif any(kw in query for kw in ["统计","汇总","总结"]):            statistics      # :226
```

省份识别是 `[p for p in PROVINCES if p in query]`(`query_router.py:214`)。

同时产出三个辅助判定:

| 方法 | 行号 | 输出 |
|---|---|---|
| `_determine_scope` | 251 | `comprehensive` / `partial` / `specific` |
| `_determine_output_format` | 260 | `province_list` / `detailed` / `comparison` / `statistics`,默认 `province_list` |
| `_assess_complexity` | 273 | `high` / `medium` / `low` |

**复杂度是累加计分**(`query_router.py:273-298`):

| 条件 | 加分 | 行号 |
|---|---|---|
| 含"所有省份/31省/全国" | +2 | 278-279 |
| 含"对比/分析/统计" | +1 | 281-282 |
| 含"详细/深入/全面" | +1 | 284-285 |
| 提及省份数 > 3 | +1 | 291-292 |

阈值:`>=3` → high、`>=1` → medium、否则 low。理论满分 5。

**批次策略**(`query_router.py:115-158`,`create_query_plan`)四路分支:

| 条件 | 策略 | 批次数 | 行号 |
|---|---|---|---|
| `all_provinces` + `high` | `province_groups` | 4(按经济区分组) | 130-134 |
| `all_provinces` | `single_batch` | 1 | 135-139 |
| 提及省份数 > 5 | `province_chunks` | `ceil(n/batch_size)` | 140-144 |
| 其他 | `single_query` | 1 | 145-147 |

**省份分组常量表**(`query_router.py:48-88`)有两套:

- `economic_zones`:4 组(东部 10 / 中部 6 / 西部 12 / 东北 3,合计 31)——被 `_create_province_group_batches:306` 使用
- `geographic`:7 组(华北 5 / 华东 7 / 华中 3 / 华南 3 / 西南 5 / 西北 5 / 东北 3,合计 31)——未被读取

**批次执行**(`query_router.py:160-205`,`execute_query_plan`)是纯串行 `for` 循环(`:176`),无并发。批次级异常被 `except` 吞掉只打日志(`:190-191`),不重试、不中断。

### 4.2 五路分层检索

`retriever.py:358-448`,`RAGRetriever.smart_retrieve`。注意此处**又做了一遍意图识别**(`identify_query_intent`,`retriever.py:111`),规则与 `query_router` 不同——它是覆盖式而非 elif 链:

```python
if all_provinces 关键词:  t = "all_provinces"      # :131
if mentioned_provinces:   t = single/multi          # :143  ← 覆盖
if 对比关键词:            t = "comparison"          # :151  ← 再覆盖
if 统计关键词:            t = "statistics"          # :157  ← 再覆盖
```

**五条检索路径与预算**:

| 意图 | 方法 | 行号 | 每省块数 | 字符预算 |
|---|---|---|---|---|
| `all_provinces` | `retrieve_for_all_provinces` | 176 | 8 | 80,000 |
| `single_province` | `retrieve_for_specific_provinces` | 220 | 30 | 40,000 |
| `multi_province` | 同上 | 220 | 15 | 60,000 |
| `comparison` | `retrieve_for_comparison` | 270 | 25(总量帽 150) | 100,000 |
| `statistics` | `retrieve_by_topic` | 322 | 全局 `top_k=120` | 80,000 |
| 其他(general) | 内联,`top_k=60` + 相邻块聚合 | 407 | — | 100,000 |

**向量检索**(`vector_store.py:218-282`,`search`)的关键实现:

```python
query_embedding = embedding_manager.encode_texts([query], show_progress=False)  # :240
search_k = min(max(top_k * 4, 200), self.index.ntotal)                          # :247
scores, indices = self.index.search(query_embedding.astype(np.float32), search_k)

for score, idx in zip(scores[0], indices[0]):                                   # :255
    if province_filter and chunk.province != province_filter:                   # :262
        continue                                                                 # ← 后置过滤
    similarity = 1.0 / (1.0 + score)                                            # :269
    results.append((chunk, similarity))
    if len(results) >= top_k: break
```

三个要点:

- **省份过滤是后置的**:先取全局 top-`search_k`,再筛省份
- **`search_k` 下限硬编码 200**
- **相似度是 L2 距离的倒数变换**`1/(1+d)`,不是余弦

全省扫描时(`retriever.py:196-206`)对 31 个省循环调用 `search`,因此 `encode_texts` 会被调用 31 次。

**相邻块聚合**(`retriever.py:61-109`,`get_adjacent_chunks`):

```python
same_doc_chunks = [c for c in self.vector_store.chunks
                   if c.source == chunk.source and c.province == chunk.province]  # :75-78
same_doc_chunks.sort(key=lambda x: getattr(x, 'chunk_id', 0))                     # :81
# 定位目标块：比较 content 全文 + start_pos
if stored_chunk.content == chunk.content and stored_chunk.start_pos == chunk.start_pos:  # :86
```

按 `chunk_id` 排序后取前后 `window` 个(默认 1)。该方法只在 `smart_retrieve` 的 **general 分支**被调用(`retriever.py:422`)。

### 4.3 上下文组装与截断

**截断**(`retriever.py:450-525`,`_truncate_results`)分两个分支:

*分支 A —— `all_provinces` 按省均分*(`:467-480`):

```python
chars_per_province = max_chars // len(result.provinces)   # :468
```

分母是**实际检索到的**省份数,不是 31。

*分支 B —— 其他情况按打分排序*(`:481-517`):

```python
def chunk_score(chunk):
    char_score = min(chunk.char_count / 500, 2.0)        # :486  取值 0~2.0
    content_score = len(chunk.content.split()) / 100     # :487  取值 0.02~0.15
    return char_score + content_score
```

排序后逐个装入,末位块若剩余空间 > 200 字符则截断填入(`:502-516`)。

**格式化**(`retriever.py:527-563`,`format_context`):按省份分组,每组加 `=== {省份} ===` 分隔头,块内用 `re.sub(r'\s+', ' ', ...)` 压缩空白。

### 4.4 Prompt 模板

`query_router.py:398-437`,`_build_prompt`。四套格式指令:

| `output_format` | 指令要点 | 行号 |
|---|---|---|
| `province_list` | 「内容必须来自政府工作报告原文,不要编造」 | 401-402 |
| `detailed` | 「1. 内容来自原文 / 2. 可适当整理归纳 / 3. 不要编造不存在的信息」 | 403-406 |
| `comparison` | 「1. 内容来自各省份报告 / 2. 可适当整理便于对比 / 3. 不要编造信息」 | 407-410 |
| `statistics` | 「1. 基于报告内容 / 2. 可适当汇总整理 / 3. 不要编造数据」 | 411-414 |

未命中格式时 `.get` 回退到 `province_list`(`:417-419`)。四套的共性是每套都有一条反幻觉约束。

**外层统一模板固定五段**(`:421-435`):

```
请根据提供的政府工作报告内容回答用户问题。
【用户问题】{query}
【输出要求】{instruction}
【重要原则】所有内容必须来自政府工作报告原文,不要编造或杜撰任何信息。
【参考资料】{context}
请基于参考资料回答问题。
```

检索上下文放在最后、紧邻结尾指令。

### 4.5 生成调用

`api_client.py`,`SiliconFlowClient`。**不使用任何厂商 SDK**。

**客户端初始化**(`api_client.py:31-53`):

```python
self.session = requests.Session()                    # :43
self.session.headers.update({                        # :46-49
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
})
```

用 `Session` 复用 TCP 连接,鉴权头只设一次。`base_url` 做 `rstrip('/')` 归一化(`:41`)。

**核心调用**(`api_client.py:55-171`,`chat_completion`):

```python
url = f"{self.base_url}/chat/completions"            # :72
payload = {                                          # :74-80
    "model": self.model,
    "messages": messages,
    "temperature": temperature,     # 默认 0.3
    "max_tokens": max_tokens,       # 默认 8192
    "stream": False,                # 硬编码，无流式路径
}
response = self.session.post(url, json=payload, timeout=timeout)   # :88-92
```

响应解析:`result["choices"][0]["message"]["content"]`(`:111`)、`result.get("usage", {})`(`:112`)。

**统一返回结构**`APIResponse`(`api_client.py:19-26`,`@dataclass`):`success` / `content` / `usage` / `error` / `response_time`。方法内用四层 `except`(`Timeout:133` → `RequestException:143` → `JSONDecodeError:153` → `Exception:163`)兜住全部异常,**永不向外抛**,调用方靠 `success` 判断成败。

**重试只存在于 `batch_process`**(`api_client.py:202-247`):

```python
while retry_count < max_retries:                     # :225  max_retries=3 含首次
    ...
    time.sleep(delay_between_requests * retry_count)  # :235  线性退避 1s、2s
```

`chat_completion` / `simple_chat` / `test_connection` 都是**一次性、无重试**的。而查询链路走的是 `simple_chat`(`query_router.py:365`),因此单次查询的 LLM 调用没有重试。

**参数来源**(`query_router.py:363-370`):从 `SILICONFLOW_CONFIG` 读 `timeout=180` / `temperature=0.3` / `max_tokens=8192`。注意 `api_client` 自身不读这三项——它们在 `chat_completion` 签名里另有硬编码默认值(`:57-59`)。

**连接自检**(`api_client.py:249-270`,`test_connection`):发中文提示「你好,请回复'连接成功'」,覆盖 `max_tokens=50` / `timeout=10`,只判断 `response.success`。这是一次真实的 LLM 调用,会消耗额度。

---

## 5. 结果聚合层

`result_aggregator.py`,447 行,纯标准库,不碰模型与向量库。

**触发条件**(`main.py:171`):

```python
if len(query_plan.batches) > 1:
    aggregated_result = self.result_aggregator.aggregate_batch_results(...)
```

单批次路径不走这一层,`processing_stats` 由 `main.py:183-187` 硬编码为 `success_rate=1.0` / `total_batches=1`。

**主流程**(`result_aggregator.py:52-134`,`aggregate_batch_results`):

```
① 过滤 success 批次                      :67
② 逐批从 content 文本反向解析省份内容      :83
③ 按省累积 targets（extend 合并）         :97
④ 逐省去重                               :100-101
⑤ 按 output_format 分派四种拼装           :104-113
⑥ 统计并返回 AggregatedResult             :116-131
```

第 ② 步是这一层的特点:**从 LLM 的自由文本输出里用正则反解结构**,而不是消费上游的结构化数据(批次自带的 `provinces` 字段在 `:84` 取出后从未使用)。

**省份解析是逐行状态机**(`result_aggregator.py:136-175`,`_parse_province_content`):维护 `current_province` 游标,命中省名的行既当标题又抽目标,未命中的行归属上一个省。

**省名识别三级**(`result_aggregator.py:177-201`):

1. `PROVINCES` 全名子串匹配(`:182-184`)
2. 单字别名子串匹配(`:187-189`),别名表在 `:33-42`,33 个键
3. 正则 `r'([^：:]+)(?:省|市|自治区)?[：:]'` + 双向子串校验(`:192-199`)

**目标抽取**(`result_aggregator.py:203-242`):

```python
clean_line = re.sub(f'^{province}[：:]?', '', clean_line)          # :213 去省名前缀
separators = ['、','，',',','；',';','。','|']                     # :216
# for/break：只用第一个命中的分隔符切分
target = re.sub(r'^[0-9]+\.?\s*', '', target)                     # :235 去序号
# 过滤：命中 target_keywords 之一，或长度 > 10
```

**去重是两段式**(`result_aggregator.py:264-289`):

```python
unique_targets = list(dict.fromkeys(targets))     # :270 精确去重，保序
# 再与已接受列表两两比相似度，> 0.8 判重并保留更长的那条  :274-288
```

**自研字符包含率相似度**(`result_aggregator.py:291-301`):

```python
common_chars = sum(1 for c in text1 if c in text2)
return common_chars / max(len(text1), len(text2))
```

不是 Jaccard、不是编辑距离,注释自称「简单的字符级相似度计算」(`:293`)。该度量不对称:`f(a,b) ≠ f(b,a)`。

**四种输出格式**:

| 方法 | 行号 | 形态 |
|---|---|---|
| `_format_as_province_list` | 303 | 每省一行 `{省}：{目标1、目标2…}`,每省最多 5 条 |
| `_format_as_detailed_report` | 319 | Markdown,H1 + 每省 `## {省}` + 编号列表 |
| `_format_as_comparison_table` | 339 | 三列 Markdown 表,主要目标取前 3 条 |
| `_format_as_statistics` | 361 | 基本统计 + 按 `target_keywords` 词频的目标类型分布(降序前 10) |

**长度优化**(`result_aggregator.py:393-436`,`optimize_for_token_limit`):

```python
max_chars = max_tokens * 1.5      # :405  注释「1个token约等于1.5个中文字符」
# 超限则逐行遍历，只保留含 31 个硬编码省名的行  :418-424
```

由 `main.py:190-193` 在内容超 6000 字符时以 `max_tokens=4000` 调用。

---

## 6. API 服务层

`API_KIT/`,主系统的 HTTP 封装。本身不含检索/嵌入/LLM 逻辑,全部委托给 `main.GovernmentReportRAG`。

### 6.1 应用结构

```python
app = FastAPI(title="政府工作报告RAG API", version="1.0.0")    # api_server.py:12
app.add_middleware(CORSMiddleware,                             # :15-21
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])
rag_system = GovernmentReportRAG()                             # :24  模块级单例
```

无 `lifespan`、无 `APIRouter`、无路由前缀、无依赖注入。CORS 是唯一中间件。

### 6.2 四个端点

| 方法 | 路径 | 行号 | 请求模型 | 响应模型 |
|---|---|---|---|---|
| POST | `/api/query` | 27 | `QueryRequest` | `QueryResponse` |
| GET | `/api/status` | 51 | — | `StatusResponse` |
| POST | `/api/setup` | 59 | `SetupRequest` | `StatusResponse` |
| GET | `/api/health` | 68 | — | `HealthResponse` |

四个都是同步 `def`(非 `async def`),FastAPI 会丢进线程池执行。

**Pydantic 模型**(`api_models.py`,共 8 个):

| 模型 | 行号 | 字段 |
|---|---|---|
| `QueryOptions` | 4 | `output_format="province_list"` / `max_results=50` / `include_stats=True` |
| `QueryRequest` | 9 | `query: str`(必填) / `options: Optional[QueryOptions]` |
| `QueryResponseData` | 13 | `content` / `provinces` / `query_type` / `output_format` / `processing_time` / `processing_stats` |
| `QueryResponse` | 21 | `success` / `data` / `message` / `error` |
| `StatusResponseData` | 27 | `is_ready` / `vector_store_built` / `api_available` / `vector_stats` |
| `StatusResponse` | 33 | 与 `QueryResponse` 同构 |
| `SetupRequest` | 39 | `force_rebuild: bool = False` |
| `HealthResponse` | 42 | `status: str = "ok"` |

所有失败路径都返回 **HTTP 200**,成败由 body 里的 `success` 表达。`HTTPException` 在 `:1` 被导入但从未 `raise`。

### 6.3 「构造」不等于「就绪」

`rag_system = GovernmentReportRAG()`(`api_server.py:24`)在 uvicorn 导入模块时同步执行,但构造函数把 `is_ready = False`(`main.py:51`)。只有 `setup_system()` 成功走到 `main.py:117` 才置 `True`。

因此进程起来后 `/api/query` 会一直返回 `success=False` + `error="系统未就绪，请先初始化。"`(`api_server.py:28-29`),**必须先 POST `/api/setup`**。

`start_all.bat` 用三步编排补这一步:

```
:8   后台起 start_api.bat
:12  timeout /t 15         ← 硬编码盲等 15 秒，无健康检查轮询
:17  PowerShell Invoke-RestMethod POST /api/setup
:21  起 start_ngrok.bat
```

### 6.4 启动方式

```bat
conda activate GovRag                                                    # start_api.bat:7
cd /d "%~dp0\.."                                                         # :16
uvicorn API_KIT.api_server:app --host 0.0.0.0 --port 8000 --reload       # :17
```

必须从项目根启动,因为 `api_server.py:3` 用的是绝对包路径 `from API_KIT.api_models import ...`,同时 `:5-9` 把上级目录 append 进 `sys.path` 以便 `from main import ...`。

**ngrok 集成是纯外部进程**(`start_ngrok.bat:8`):

```bat
ngrok-v3-stable-windows-amd64\ngrok.exe http 8000
```

Python 侧零集成——无 `pyngrok`、无 4040 本地 API 调用、无公网 URL 回写。URL 只在 ngrok 控制台窗口显示。

三个启动脚本都是 `.bat`(cmd 语法 + `chcp 65001` + conda + PowerShell),**无 Linux/macOS 对应脚本**。

---

## 7. 配置体系全量说明

`config/config.example.py`,106 行。纯 Python 模块形式(非 YAML/env),7 个模块级常量 + 1 个函数。

`config/config.py` 已列入 `.gitignore:15`,因此密钥不入库,`config.example.py` 是仓库中唯一可见的配置文件。

**路径基准**:`PROJECT_ROOT = Path(__file__).parent.parent`(`:12`),其余路径全部由它派生。

### 7.1 全量配置表

> "消费者"列标注实际读取该项的代码位置;标 ❌ 的项在全仓库无任何消费者。

**`SILICONFLOW_CONFIG`**(`:15`)

| 键 | 值 | 消费者 |
|---|---|---|
| `api_key` | `"your-api-key-here"`(占位符,需手改) | `api_client.py:280` |
| `base_url` | `https://api.siliconflow.cn/v1` | `api_client.py:281` |
| `model` | `Tongyi-Zhiwen/QwenLong-L1-32B` | `api_client.py:282` |
| `temperature` | `0.3` | `query_router.py:368` |
| `max_tokens` | `8192` | `query_router.py:369` |
| `timeout` | `180` | `query_router.py:367` |

**`EMBEDDING_CONFIG`**(`:25`)

| 键 | 值 | 消费者 |
|---|---|---|
| `model_path` | `PROJECT_ROOT/models/jina-embeddings-v4` | `embedding_manager.py:48` |
| `model_name` | `jinaai/jina-embeddings-v4` | ❌ |
| `max_length` | `8192` | ❌ |
| `trust_remote_code` | `True` | ❌ 代码里硬编码 `True` |
| `device` | `"cuda"` | ❌ 靠 `torch.cuda.is_available()` 自动探测 |

**`DATA_PATHS`**(`:34`)

| 键 | 值 | 消费者 |
|---|---|---|
| `raw_documents` | `r"您的文档路径"`(占位符,需手改) | `main.py:75`、`rebuild_index.py:33` |
| `processed_data` | `data/processed` | `main.py:81,92` |
| `vector_store` | `data/vectors` | `vector_store.py:363` |
| `models` | `models/` | `ensure_directories` |

**`DOCUMENT_CONFIG`**(`:42`)

| 键 | 值 | 消费者 |
|---|---|---|
| `chunk_size` | `1000` | `main.py:76` |
| `chunk_overlap` | `200` | `main.py:77` |
| `min_chunk_length` | `100` | ❌ |

**`RETRIEVAL_CONFIG`**(`:49`)

| 键 | 值 | 消费者 |
|---|---|---|
| `top_k` | `60` | ❌ |
| `similarity_threshold` | `0.7` | ❌ 检索侧无阈值过滤 |
| `max_contexts_per_query` | `100000` | `retriever.py:440` |
| `single_province.top_k_per_province` | `30` | `retriever.py:236` |
| `single_province.max_chars` | `40000` | `retriever.py:385` |
| `multi_province.top_k_per_province` | `15` | `retriever.py:238` |
| `multi_province.max_chars` | `60000` | `retriever.py:391` |
| `all_provinces.top_k_per_province` | `8` | `retriever.py:188` |
| `all_provinces.max_chars` | `80000` | `retriever.py:379` |
| `comparison.top_k_per_province` | `25` | `retriever.py:286` |
| `comparison.max_total` | `150` | `retriever.py:284` |
| `comparison.max_chars` | `100000` | `retriever.py:397` |
| `topic.top_k` | `120` | `retriever.py:336` |
| `topic.max_chars` | `80000` | `retriever.py:403` |

**`QUERY_CONFIG`**(`:87`)

| 键 | 值 | 消费者 |
|---|---|---|
| `batch_size` | `8` | `query_router.py:323` |
| `max_retries` | `3` | ❌(`api_client.py:205` 是同值的函数默认参数,无关联) |
| `timeout` | `120` | ❌ 实际生效的是 `SILICONFLOW_CONFIG.timeout=180` |

**`PROVINCES`**(`:94-99`):31 个省级行政区**简称**列表(`"内蒙古"` 而非 `"内蒙古自治区"`),不含港澳台。因为省份识别是纯 `in` 子串匹配,简称形式是必要的。

### 7.2 `ensure_directories()`

`config.example.py:102-106`:

```python
for path in DATA_PATHS.values():
    if isinstance(path, Path):                    # :105
        path.mkdir(parents=True, exist_ok=True)
```

`isinstance(path, Path)` 判断使得 `raw_documents`(raw 字符串占位符)被跳过,实际只创建 `processed_data` / `vector_store` / `models` 三个目录。

不自动调用,由 `main.py:42` 与 `rebuild_index.py:22` 显式触发。

### 7.3 检索预算的调参历史

`RETRIEVAL_CONFIG` 每一项都带"从 X 增加到 Y"式的行内注释,完整保留了一次调参记录,全部方向都是放大 3~6 倍:

| 项 | 原值 | 现值 |
|---|---|---|
| `top_k` | 20 | 60 |
| `max_contexts_per_query` | 16,000 | 100,000 |
| `single_province.top_k_per_province` | 10 | 30 |
| `multi_province.top_k_per_province` | 6 | 15 |
| `all_provinces.top_k_per_province` | 3 | 8 |
| `comparison.top_k_per_province` | 8 | 25 |
| `comparison.max_total` | 50 | 150 |
| `topic.top_k` | 60 | 120 |

五种场景的字符预算并非单调:`single 40K < multi 60K < all_provinces 80K = topic 80K < comparison 100K`,其中 `comparison` 恰好顶到全局上限 `max_contexts_per_query`。

---

## 8. 部署形态与硬件要求

### 8.1 两种形态

| 形态 | 入口 | 命令 |
|---|---|---|
| **交互式 CLI** | `main.py:242`(`main()`) | `python main.py` |
| **HTTP 服务** | `API_KIT/api_server.py` | `uvicorn API_KIT.api_server:app --host 0.0.0.0 --port 8000` |

另有运维脚本 `rebuild_index.py`,专门解决 embedding 维度不匹配:先向模型问出真实维度(`:27`),清空 `data/vectors/` 下所有文件(`:57-60`),再用该维度重建并做一次搜索自检(`:89`)。

**CLI 交互**(`main.py:266-306`):`input()` 循环,退出词 `quit` / `exit` / `退出`(`:270`,大小写不敏感),空输入 `continue`,循环内异常只打印不退出。无 argparse/click。

### 8.2 硬件要求

README 标注:Python 3.10+ / NVIDIA RTX 3060 或更高 / 内存 16GB(推荐 32GB)/ 硬盘 20GB / CUDA 11.8+。

实际计算分布是**混合部署**:

- Embedding 推理在 GPU(`device` 自动探测,`embedding_manager.py:54`)
- 向量索引与检索在 CPU(`faiss-cpu==1.7.4`)
- 生成模型在云端(硅基流动 API)

无 GPU 时 `embedding_manager.py:54` 会自动回落 CPU。

### 8.3 首次部署的五个阻断项

以下均为实测确认:

**① 模型权重不在仓库。** `.gitignore` 排除了 `models/jina-embeddings-v4/.../blobs/` 与 `snapshots/`,仓库中 `models/` 只有 36K 空壳。而 `embedding_manager.py:108` 用 `local_files_only=True`,`:90-98` 校验目录与 `config.json` 存在,缺失即 `return False`。需先手动下载 jina-embeddings-v4(约 7.5GB)。

**② `config/config.py` 不存在。** 只有 `.example.py`。全项目的 config 导入都写作 `from config.config import ...`(多为函数内延迟导入),未复制前会在首次调用时 `ImportError`。需手改两个占位符:`api_key`、`raw_documents`。

**③ zip 内文件名是 GBK 编码。** 直接解压得到乱码文件名,使 `extract_province_from_filename`(第一优先级)全数失效,静默 fallback 到正文识别。

**④ `jieba==0.42.1` 在新版 setuptools 下构建失败。** 而它在全项目**零调用**——`data_processor.py:18` 只有 import,但该 import 会阻断整个模块加载。

**⑤ 启动脚本仅支持 Windows。** 三个 `.bat` 依赖 cmd 语法 + `chcp 65001` + `conda activate GovRag` + PowerShell;`ngrok.exe` 也是 windows-amd64 版,且因 GitHub 25MB 单文件限制被 `.gitignore:72` 排除,全新 clone 上 `start_ngrok.bat` 会直接失败。

### 8.4 免模型的验证路径

`mvp/setup_and_run.py` 提供一条不需要 GPU、不需要 Jina 权重、不需要 API key 的验证路径:自动装依赖、解压数据、修复 GBK 文件名,并运行四个演示脚本。向量层用 TF-IDF 替代。

```bash
python mvp/setup_and_run.py
```

---

## 9. 技术选型的理由与权衡

### 9.1 Embedding 本地 + 生成走云

这是整个架构最主要的成本分配决策。

| | Embedding(Jina v4) | 生成(QwenLong-L1-32B) |
|---|---|---|
| 部署 | 本地 GPU | 硅基流动 API |
| 参数量 | 约 3.8B | 32B |
| 调用频次 | 建库时 855 次 + 每查询 1~31 次 | 每查询 1~4 次 |

把 3.8B 的编码器放本地(消费级显卡即可承载),把 32B 的算力成本转成 API 按量付费。同时 embedding 本地化也规避了把全部语料上传第三方。

### 9.2 `IndexFlatL2` 而非 IVF

`vector_store.py:66` 选暴力精确检索,IVF 的代码以注释形式保留在 `:68-71`。

理由是数据量级:855 个块在 CPU 上做全量 L2 计算是毫秒级,IVF 的聚类近似只会引入召回损失而无收益。同理选 `faiss-cpu` 而非 `faiss-gpu`,省掉 CUDA 编译。

### 9.3 长上下文模型是 10 万字方案的前提

`RETRIEVAL_CONFIG.max_contexts_per_query = 100000` 字符,`comparison` 场景恰好顶到这个上限。要消化这个量级的输入,生成模型必须支持超长上下文——这是选 QwenLong-L1-32B 的直接原因(`config.example.py:18` 注释即写"使用支持更长上下文的模型")。

配套参数:`temperature=0.3`(注释"降低温度以获得更准确的数据输出")、`timeout=180`(为长上下文处理留足时间)。

### 9.4 SDPA 替代 FlashAttention2

`requirements.txt:22` 注释禁用 `flash-attn`,理由写在 `:21`:Windows 下可能需要预编译包,而 PyTorch 2.x 的 `attn_implementation="sdpa"` 最简单直接且加速显著。

代码层面 `sdpa` 确为默认值(`embedding_manager.py:31`),并保留三级降级链以适配不同环境。

### 9.5 规则式意图识别而非模型

`query_router` 与 `retriever` 的意图识别全部是中文关键词子串匹配,零依赖、零延迟、完全可解释。代价是覆盖面受关键词表限制,且两处实现需手工保持同步。

---

## 10. 已知问题与改进优先级

本节汇总在真实语料上验证过的问题。验证脚本与完整数据见 [`mvp/README.md`](mvp/README.md)。

### 10.1 架构层:单省查询时检索层不产生作用

**这是影响最大的一条。**

`RETRIEVAL_CONFIG.single_province.top_k_per_province = 30`,但实测各省块数中位仅 28:

```
各省块数：最少 16、中位 28、最多 50、平均 27.6
总块数 ≤ 30 的省份：22 / 31
```

对这 22 个省做单省查询时,配额大于实际块数,该省全部块无条件入选——排序、过滤、打分均不产生作用,等价于**将该省报告全文投喂给模型**。

这解释了此前"调大 `top_k` 后召回问题消失"的机制:并非检索质量提升,而是退化为全文投喂;时延与 token 成本的上升同源于此。

**改进方向**——按查询范围分流:

| 范围 | 建议 |
|---|---|
| 单省(1.3 万字) | 直接取该省全文,不走检索 |
| 2~5 省(约 6 万字) | 同上,长上下文模型可容纳 |
| 全省 / 主题 | 走 RAG |

### 10.2 P0 —— 修复成本低、收益直接

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| 1 | **query 用 passage 前缀编码** | `vector_store.py:240` | Jina v4 是非对称检索模型,query 与 passage 用不同前缀。该行未传 `prompt_name`,走默认值 `"passage"`(`embedding_manager.py:181`)。而写法正确的 `encode_query()`(`embedding_manager.py:253`)全仓库零调用。**排序质量受直接影响。** |
| 2 | **同一 query 被编码 31 次** | `retriever.py:196-206` | 全省扫描循环 31 个省,每次 `search` 都重新 `encode_texts([query])`(`vector_store.py:240`)。按 README 自述性能(5 文本/0.56s)估算,白耗 10~15 秒。把编码提到循环外即可。 |
| 3 | **省份过滤后置** | `vector_store.py:247-274` | 先取全局 top-`search_k` 再筛省份,`search_k` 下限硬编码 200。实测每省配额平均缺口 **26%**(应得 248 块,实得 178~192)。随索引规模恶化:扩容至 8550 块时缺口 37.9%,**10 个省整省查不到**。修复方向是 pre-filter(按省分建子索引或用 FAISS `IDSelector`)。 |

### 10.3 P1 —— 功能与声明不符

| # | 问题 | 位置 | 实测数据 |
|---|---|---|---|
| 4 | **密度打分对中文失效** | `retriever.py:487` | `len(content.split())/100` 按空白分词,中文无空格,实测取值 0.02~0.15;同式 `char_score` 取值 0~2.0,差两个数量级。截断退化为纯按长度排序。样本中数字最密集的块(甘肃,58 个数字)原版排**第 34/400**,加数字密度后排**第 1**。 |
| 5 | **两处意图识别规则冲突** | `query_router.py:218` vs `retriever.py:131` | 前者 elif 链、后者覆盖式,6 条测试中 **3 条判定不同**。实际生效的是 `retriever` 那一遍;`query_router` 的 `comparison` 分支因省份判断在前而**不可达**。 |
| 6 | **相邻块聚合仅在 general 分支生效** | `retriever.py:422` | 五条主检索路径(`all_provinces`/`single_province`/`multi_province`/`comparison`/`statistics`)均未调用 `get_adjacent_chunks`。要走到 general 分支,query 必须既不提省份名也不含任何范围关键词。 |
| 7 | **批次 query 被模板覆写** | `query_router.py:307,330` | `_create_province_group_batches` 与 `_create_province_chunk_batches` 都接收 `query` 但从未使用,批次 query 被重写为"请列出…的主要工作目标"。用户问"各省环保目标"若走分组分批,发给检索和 LLM 的是"主要工作目标",语义漂移。 |

### 10.4 P2 —— 稳定性与一致性

| # | 问题 | 位置 |
|---|---|---|
| 8 | `chunk_type == "title"` 永不产生:判定要 `len < 100`,实测最短块 303 字。`target` 占 55.7%,使 `retrieve_by_topic(chunk_type="target")` 只筛掉 44% | `data_processor.py:196` |
| 9 | `optimize_for_token_limit` 截断分支会 `TypeError`:`max_chars` 是 float(`max_tokens * 1.5`),`line[:remaining_chars]` 要求 int | `result_aggregator.py:405,432` |
| 10 | `_format_as_statistics` 除零风险:`total_targets/total_provinces` 未判非零,有成功批次但零省份时抛 `ZeroDivisionError` | `result_aggregator.py:382` |
| 11 | 日志目录竞态:`logging.basicConfig` 在模块导入期创建 `logs/government_rag.log`,而 `ensure_directories()` 到 `__init__` 才执行;`logs/` 不存在时导入即 `FileNotFoundError` | `main.py:24-31` vs `:42` |
| 12 | 单批次路径 `processing_stats` 是硬编码假数据(`success_rate=1.0`) | `main.py:183-187` |
| 13 | 长度优化单位混用:用字符数 6000 判断,传 `max_tokens=4000` | `main.py:190` |
| 14 | API 无任何鉴权,`allow_origins=["*"]` 与 `allow_credentials=True` 并存(按 CORS 规范该组合无法生效);匿名可调 `/api/setup` 触发全量重建。叠加 ngrok 公网暴露风险 | `api_server.py:15-21` |
| 15 | `--reload` 与模块级单例冲突:任何改动都会重建 RAG 实例、`is_ready` 归零。文档推荐的 `--workers 4` 会产生 4 个互不相干的单例,而 `/api/setup` 只命中其中一个 | `start_api.bat:17` |
| 16 | `/api/health` 是空壳,无条件返 `ok`,不可用作就绪探针 | `api_server.py:69` |
| 17 | `QueryOptions` 三个字段(`output_format`/`max_results`/`include_stats`)暴露在 OpenAPI 文档中但服务端从未读取 | `api_models.py:4-7` |
| 18 | 自研相似度不对称且对中文易误判:`f('发展发展发展','发展')=1.0`;中文报告里"发展/建设/推进/提升"高频复用,0.8 阈值会误杀语义不同的条目 | `result_aggregator.py:291` |
| 19 | `numpy==1.24.3`(2023)被精确锁死,同时要求 `torch>=2.5.0`、`sentence-transformers>=3.0.0`,存在装不上或 ABI 冲突风险 | `requirements.txt:5` |
| 20 | 四个依赖声明但零 import:`pandas` / `python-dotenv` / `openai` / `accelerate` | `requirements.txt:6,8,12,20` |
| 21 | `README.md:305` 示例命令调用的 `check_optimization_support()` 方法不存在,会 `AttributeError` | `README.md:305` |
| 22 | 省份列表在三处重复定义:`config.PROVINCES`、`result_aggregator.py:209-212`、`:419-424` | — |

### 10.5 评测缺口

当前没有可复现的量化评测。已有的验证是 bad case 复测——只能证明"已知的错被修好了",无法给出整体质量的分母。

对 RAG 尤其不适用:主要失效方式是**漏检**,而漏检对用户不可见(实测 29/31 个省都提到"低空经济",系统若只答 8 个省,用户没有能力发现问题)。

建议补齐:100 条 query 覆盖五类场景,每条把标准答案拆成信息点清单,计算三个指标——

| 指标 | 抓什么 |
|---|---|
| 答案完整率(答出的点/应有的点) | 漏 |
| 关键数字准确率 | 错与编 |
| 检索召回率 Recall@k | 分清是检索没捞到,还是模型没用上 |

第三个指标能定位病根在哪一层,是区分"改检索"与"改 prompt"的依据。

---

## 附:文件职责索引

| 文件 | 行数 | 职责 | 本文章节 |
|---|---|---|---|
| `main.py` | — | 顶层编排 + 交互式 CLI | 4, 8.1 |
| `rebuild_index.py` | — | 索引重建运维脚本 | 8.1 |
| `src/data_processor.py` | — | docx 解析、切块、省份标注 | 3.1, 3.2 |
| `src/embedding_manager.py` | 388 | Jina v4 加载与编码(主链路) | 3.3 |
| `src/embedding_manager_st.py` | — | SentenceTransformers 实现(未引用) | 2.2 |
| `src/vector_store.py` | — | FAISS 索引构建、落盘、检索 | 3.4, 4.2 |
| `src/retriever.py` | — | 五路分层检索、相邻块聚合、截断 | 4.2, 4.3 |
| `src/query_router.py` | 481 | 意图识别、批次规划、prompt 构建 | 4.1, 4.4 |
| `src/api_client.py` | 286 | 硅基流动 REST 客户端 | 4.5 |
| `src/result_aggregator.py` | 447 | 多批次结果聚合与格式化 | 5 |
| `config/config.example.py` | 106 | 全量配置模板 | 7 |
| `API_KIT/api_server.py` | — | FastAPI 应用与四个端点 | 6 |
| `API_KIT/api_models.py` | — | 8 个 Pydantic 模型 | 6.2 |
| `API_KIT/*.bat` | — | Windows 启动脚本 | 6.4 |
| `mvp/` | — | 原理演示与缺陷验证脚本 | 8.4, 10 |
