# 🏛️ 政府工作报告RAG系统

## 📋 项目简介

本项目是一个基于RAG（Retrieval-Augmented Generation）技术的政府工作报告智能问答系统，专门解决**信息检索不完整**和**多省份对比数据不够详细**的核心问题。通过创新的**智能分层检索架构**和**上下文窗口最大化利用**策略，实现了高效的大规模文档处理和精准的智能问答。

### 🎁 开箱即用
- **📁 完整数据集**：已包含31省区市政府工作报告数据（docs文件夹）
- **🚀 一键部署**：解压数据即可运行，无需额外准备文档
- **💡 智能优化**：经过深度调优的检索和问答系统

### 🎯 核心问题与解决方案

#### 原始问题
1. **信息完整性不足**：系统读不完整篇政府工作报告就回答问题，明明文章里有用户要的信息
2. **多省份对比数据不够详细**：涉及多个省份对比时，只能返回若干内容，数据不够详细

#### 解决方案
通过**阶段1无重切块优化方案**，我们实现了：

1. **🔍 检索深度大幅提升**
   - 单省份查询：从10个块提升到30个块（+200%）
   - 多省份查询：从6个块提升到15个块（+150%）
   - 对比查询：从8个块提升到25个块（+213%）
   - 通用检索：从20个块提升到60个块（+200%）

2. **📈 上下文窗口显著扩大**
   - 总上下文：从16,000字符提升到100,000字符（+525%）
   - 平均容量提升：337.8%
   - 充分利用长上下文模型的能力

3. **🚀 系统功能增强**
   - 新增相邻块聚合功能，确保上下文连续性
   - 优化智能截断策略，保留高价值信息
   - 强化Prompt工程，确保输出详细准确
   - 完善数据结构，支持更多属性

## 📊 优化成果总览

### 核心指标提升
- **平均信息量提升**: 100.0%
- **平均检索量提升**: 100.0% 
- **上下文容量提升**: 337.8%
- **API输出能力提升**: 适配模型限制到8192 tokens

### 具体配置提升对比

| 配置项 | 优化前 | 优化后 | 提升幅度 |
|--------|--------|--------|----------|
| 通用top_k | 20 | 60 | +200% |
| 最大上下文 | 16,000字符 | 100,000字符 | +525% |
| 单省份块数 | 10 | 30 | +200% |
| 多省份块数 | 6 | 15 | +150% |
| 对比查询块数 | 8 | 25 | +213% |
| API max_tokens | 20,480 | 8,192 | 适配模型限制 |
| API timeout | 60s | 180s | +200% |

## 🛠️ 技术架构

```
政府工作报告RAG系统（优化版）
├── 数据处理层
│   ├── Word文档解析 (python-docx)
│   ├── 智能文本分块和预处理
│   └── 省份识别和分类
├── 向量化存储层
│   ├── Jina Embeddings v4 (本地部署，支持FlashAttention2+SDPA双重优化，强制使用本地模型)
│   ├── FAISS向量数据库（增强搜索能力）
│   └── 语义检索引擎（支持大量检索，内存高效）
├── 智能查询层
│   ├── 查询意图识别
│   ├── 智能分层检索策略
│   ├── 相邻块聚合机制
│   └── 检索结果路由
├── 结果聚合层
│   ├── 优化截断算法
│   ├── 信息密度评分
│   └── 详细格式化输出
├── API交互层
│   └── 硅基流动 Tongyi-Zhiwen/QwenLong-L1-32B（长上下文）
└── RESTful API服务层 (API_KIT)
    ├── FastAPI服务器 (跨域支持、健康检查)
    ├── 智能查询接口 (POST /api/query)
    ├── 系统状态接口 (GET /api/status)
    ├── 系统初始化接口 (POST /api/setup)
    └── 内网穿透支持 (ngrok集成)
```

## ✅ 功能特性

### 核心功能

1. **全省份查询**：支持"列出各省主要工作目标"等全量查询
2. **单省份深度查询**：支持"河南2025年重点工作有哪些"等详细查询
3. **多省份对比分析**：支持省份间的详细数据对比
4. **统计汇总分析**：支持各省数据的统计和汇总
5. **主题专项查询**：支持特定主题的跨省份查询

### 输出格式

- **省份列表格式**：`省份：具体数据1、具体数据2...`（包含详细数字）
- **详细报告格式**：包含所有量化指标和具体措施
- **对比表格格式**：详细的省份间数据对比
- **统计汇总格式**：完整的数据统计和分析

### 技术特性

- **智能分层检索**：根据查询复杂度动态调整检索策略
- **相邻块聚合**：自动获取相关块的上下文信息
- **优化截断算法**：保留信息密度最高的内容
- **强化Prompt工程**：确保输出详细完整的数据
- **长上下文支持**：充分利用100K字符的上下文窗口
- **本地模型优化**：强制使用本地模型文件，避免网络下载，提升启动速度
- **RESTful API服务**：完整的HTTP接口支持，便于系统集成和前端调用

## 📁 数据说明

### 内置数据集
本项目已包含完整的31省区市政府工作报告数据，存放在 `docs/31省区市政府工作报告.zip` 中：

| 区域 | 省份 | 文档格式 |
|------|------|----------|
| **华北** | 北京、天津、河北、山西、内蒙古 | .docx |
| **东北** | 辽宁、吉林、黑龙江 | .docx |
| **华东** | 上海、江苏、浙江、安徽、福建、江西、山东 | .docx |
| **华中** | 河南、湖北、湖南 | .docx |
| **华南** | 广东、广西、海南 | .docx |
| **西南** | 重庆、四川、贵州、云南、西藏 | .docx |
| **西北** | 陕西、甘肃、青海、宁夏、新疆 | .docx |

### 数据特点
- **📊 数据完整性**：覆盖全国31个省区市，无遗漏
- **📅 时效性**：最新年度政府工作报告
- **📋 标准化**：统一的Word文档格式，便于处理
- **🔍 可检索性**：包含详细的经济指标、发展目标、重点项目等信息

### 使用方式
```bash
# 1. 解压数据文件
cd docs
unzip "31省区市政府工作报告.zip"

# 2. 数据会解压到 docs/31省区市政府工作报告/ 目录
# 3. 配置文件中设置路径为此目录即可
```

## ⚡ 快速开始

### 💬 网页聊天前端（推荐，1 分钟跑起来）

无需 GPU、无需模型权重、无需 API Key，用仓库自带的 855 块数据即可体验完整交互：

```bash
pip install fastapi uvicorn scikit-learn numpy
python API_KIT/web_server.py --demo
# 浏览器打开 http://127.0.0.1:8000
```

界面包含聊天气泡、引用来源面板（省份 / 相似度 / 原文摘要）、分阶段进度态和示例问题。

- **Demo 模式**：TF-IDF 检索 + 原文摘编；设置环境变量 `SILICONFLOW_API_KEY` 后自动改用 LLM 生成完整答案
- **完整模式**：按下方步骤部署后，去掉 `--demo` 参数即自动启用（失败会自动降级回 Demo 模式）

### 🐳 用 Docker 启动（环境隔离，推荐）

```bash
docker compose up -d demo     # Demo 模式，约 3 分钟
docker compose up -d full     # 完整模式，需先下载权重到 ./models
```

> **想部署到云服务器？** 见 **[DEPLOY_CN.md](DEPLOY_CN.md)** —— 从开通服务器、放行端口、安装 Docker 到两条部署路线的完整教程，含访问控制、成本管理与常见问题排查。

### 📏 评测

```bash
python eval/run_eval.py                               # 评测 Demo 后端，约 5 秒，无需 GPU / Key
python eval/run_eval.py --api http://127.0.0.1:8000   # 评测正在运行的服务（含完整系统）
```

57 题评测集，按意图、检索、答案三层打分，并把每个信息点归因到检索层或生成层。评测方案、基线结果与一次完整的改进验证见 **[EVAL_CN.md](EVAL_CN.md)**。

### 🚀 完整模式（Jina v4 + FAISS + LLM）一键部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载 Jina v4 权重（约 7.5GB，只需一次；国内先设 HF_ENDPOINT=https://hf-mirror.com）
pip install -U huggingface_hub
hf download jinaai/jina-embeddings-v4 --local-dir models/jina-embeddings-v4

# 3. 一键预检 + 建索引（自动生成 config、检测 GPU/CPU、构建 FAISS 索引）
export SILICONFLOW_API_KEY=你的密钥   # 可选，不设则无法生成答案但可建索引
python setup_full.py

# 4. 启动
python API_KIT/web_server.py
```

预期耗时：建索引 GPU 约 2~5 分钟、CPU 约 15~40 分钟（只建一次）；查询时 CPU 每次多 1~3 秒编码时间。前端顶栏显示「完整系统 · Jina v4」即部署成功。

### 5分钟快速体验

```bash
# 1. 克隆项目
git clone https://github.com/alexzhu0/government-report-rag.git
cd government-report-rag

# 2. 解压数据
cd docs && unzip "31省区市政府工作报告.zip" && cd ..

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制配置文件
copy config\config.example.py config\config.py  # Windows
# cp config/config.example.py config/config.py    # Linux/Mac

# 5. 编辑配置文件，填入您的API密钥
# 编辑 config/config.py，设置：
# - api_key: 您的硅基流动API密钥
# - raw_documents: "docs/31省区市政府工作报告"

# 6. 运行系统
python main.py
```

### 🎯 立即体验查询
```
🔍 请输入查询: 河南2025年重点工作有哪些
🔍 请输入查询: 对比广东和江苏的产业发展
🔍 请输入查询: 各省GDP增长目标是多少
```

## 🚀 详细安装部署

### 环境要求

- **Python 3.10+**
- **NVIDIA GPU**：RTX 3060或更高（推荐）
- **内存**：至少16GB（推荐32GB）
- **硬盘空间**：至少20GB
- **CUDA**：11.8+（用于GPU加速）

## 🌐 API服务部署

### 📋 API_KIT 简介

本项目提供了完整的RESTful API服务模块（`API_KIT/`），支持通过HTTP接口调用RAG系统功能，方便前端应用、自动化工具和第三方系统集成。

#### 🎯 主要功能
- **智能查询接口**: 支持自然语言查询政府工作报告
- **系统状态监控**: 实时获取系统运行状态和统计信息
- **系统初始化**: 远程初始化和重建向量索引
- **内网穿透**: 集成ngrok支持外网访问
- **跨域支持**: 完整的CORS配置，支持前端调用

#### 🚀 快速启动API服务

```bash
# 方式1: 一键启动（推荐）
cd API_KIT
start_all.bat  # 自动启动API服务和ngrok

# 方式2: 手动启动
conda activate GovRag
cd API_KIT
start_api.bat
```

#### 📡 API接口示例

```bash
# 查询接口
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "河南省2025年重点工作有哪些"}'

# 系统状态
curl -X GET "http://localhost:8000/api/status"

# 访问API文档
# http://localhost:8000/docs
```

#### 📚 详细文档

API服务的完整配置、部署和使用说明，请参考：
**[API_KIT/README.md](API_KIT/README.md)** - 包含详细的：
- 完整的API接口文档和示例
- 多种启动方式和环境配置
- 客户端调用示例（Python、JavaScript、cURL）
- 内网穿透配置和使用
- 安全配置和性能优化
- 故障排除和开发指南

### ⚡ 高效注意力机制优化

本项目采用了先进的注意力机制优化技术，显著提升了向量计算效率和内存使用率：

#### 🚀 FlashAttention2 的作用和优势

**FlashAttention2** 是一种内存高效的注意力计算算法，为本项目的 Jina Embeddings v4 模型提供了显著的性能提升：

- **🔥 内存效率提升**：相比标准注意力机制，内存使用减少 50-80%
- **⚡ 计算速度加速**：在长序列处理中速度提升 2-4 倍
- **📊 支持更长序列**：能够处理更长的文档块，提升检索质量
- **🎯 精度保持**：在提升效率的同时保持计算精度不变
- **💡 动态优化**：根据硬件特性自动优化计算策略

#### 🧠 SDPA（Scaled Dot-Product Attention）优化的意义

**SDPA优化** 是PyTorch 2.0+引入的原生高效注意力实现，本项目已成功启用并充分利用了其优势：

- **🔧 硬件加速**：充分利用现代GPU的Tensor Core和Memory Hierarchy
- **📈 吞吐量提升**：在批处理场景下显著提升处理吞吐量（实测：5个文本0.56秒）
- **🎛️ 自适应优化**：根据输入大小和硬件特性自动选择最优实现
- **🔋 能耗降低**：更高效的计算路径降低GPU功耗
- **🛡️ 数值稳定性**：改进的数值计算确保长序列处理的稳定性
- **✅ 已验证启用**：系统默认使用SDPA，并在加载失败时自动降级到标准attention

#### 💻 没有GPU/FlashAttention2时的可选方案

如果您的环境不支持GPU或FlashAttention2，系统提供了以下兼容方案：

**方案1：CPU模式运行**
```python
# 在 config/config.py 中设置
EMBEDDING_CONFIG = {
    "device": "cpu",  # 改为CPU模式
    "model_name": "jinaai/jina-embeddings-v4",
    # 其他配置保持不变
}
```

**方案2：标准注意力机制**
```bash
# 系统已启用SDPA优化，如果SDPA失败会自动降级使用标准attention
# 性能对比（实测数据）：
# - SDPA优化: 100% 性能基准（5个文本0.56秒）
# - 标准Attention: 70-80% 性能
# - CPU模式: 30-40% 性能
```

**方案3：轻量化配置**
```python
# 针对低配置环境的优化设置
RETRIEVAL_CONFIG = {
    "top_k": 30,  # 减少检索块数量
    "max_contexts_per_query": 50000,  # 降低上下文长度
    # 适合8GB显存或CPU运行
}
```

**环境检测和自动适配**
```bash
# 系统启动时会自动检测并选择最佳配置
python -c "from src.embedding_manager import get_embedding_manager; get_embedding_manager().check_optimization_support()"
```

**性能对比表**
| 配置方案 | GPU要求 | 内存使用 | 处理速度 | 实测性能 | 推荐场景 |
|---------|---------|----------|----------|----------|----------|
| SDPA + GPU | RTX 3060+ | 8GB | 最快 | 5文本/0.56s | 生产环境（已启用） |
| 标准Attention + GPU | GTX 1660+ | 6GB | 中等 | 5文本/0.8s | 兼容性优先 |
| CPU模式 | 无GPU | 系统内存 | 较慢 | 5文本/2-3s | 纯CPU环境 |

### 1. 克隆项目

```bash
git clone https://github.com/alexzhu0/government-report-rag.git
cd government-report-rag
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置设置

编辑 `config/config.py`：

```python
# 硅基流动API配置
SILICONFLOW_CONFIG = {
    "api_key": "your-api-key-here",  # 请替换为您的API密钥
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "Tongyi-Zhiwen/QwenLong-L1-32B",
    "temperature": 0.3,
    "max_tokens": 8192,
    "timeout": 180
}

# 原始文档路径
DATA_PATHS = {
    "raw_documents": r"您的文档路径"  # 请替换为实际路径
}
```

### 4. 准备数据

**方式1：使用提供的数据（推荐）**

我们已经为您准备了31省区市的政府工作报告数据：

```bash
# 解压数据文件
cd docs
unzip "31省区市政府工作报告.zip"
```

解压后会得到31个省份的政府工作报告Word文档，包括：
- 北京、天津、河北、山西、内蒙古
- 辽宁、吉林、黑龙江、上海、江苏
- 浙江、安徽、福建、江西、山东
- 河南、湖北、湖南、广东、广西
- 海南、重庆、四川、贵州、云南
- 西藏、陕西、甘肃、青海、宁夏、新疆

然后更新配置文件中的路径：
```python
DATA_PATHS = {
    "raw_documents": r"docs/31省区市政府工作报告",  # 使用提供的数据
    # ... 其他配置
}
```

**方式2：使用自定义数据**

如果您有其他政府工作报告数据，请将Word文档（.docx格式）放入指定目录，并在配置文件中设置路径。

### 5. 运行系统

```bash
python main.py
```

首次运行会自动：
1. 🔍 检测并加载本地Jina Embeddings v4模型（优先使用本地模型，避免网络下载）
2. 📚 处理Word文档并分块
3. 🔨 构建FAISS向量索引
4. 🔗 测试API连接

**注意**：系统已优化为优先使用本地模型文件，如果models目录中已有完整的模型文件，将直接使用本地模型，无需网络下载。

## 📝 使用示例

### 启动系统

```bash
python main.py
```

### 查询示例

#### 单省份详细查询
```
🔍 请输入查询: 河南2025年重点工作有哪些

📝 查询结果:
类型: single_province
格式: province_list
省份数: 1
处理时间: 23.97s
------------------------------

**河南：**
1. **经济增长目标**：GDP增长5.5%左右，规上工业增加值增长7%左右...
2. **消费提振**：更新汽车50万辆、家电800万台，实施设备更新项目3000个...
3. **重大项目投资**：省重点项目1000个，完成投资1万亿元...
...（包含14个详细分类的具体数据点）

📊 处理统计:
成功率: 100.0%
检索块数: 20个（优化前：10个）
上下文字符: 16,775字符
```

#### 多省份对比查询
```
🔍 请输入查询: 对比广东和江苏的产业发展

📝 查询结果:
类型: multi_province
格式: comparison
省份数: 2
处理时间: 18.45s
------------------------------

详细的对比分析，包含：
- 具体数字对比表格
- 政策措施差异分析
- 发展重点深度比较
- 投资规模精确对比
...（每省15个块，总计30个块的丰富信息）
```

## 📁 项目结构

```
government_report_rag/
├── config/
│   └── config.py              # 系统配置（已优化）
├── src/                       # 核心模块（已清理）
│   ├── data_processor.py      # 文档处理（增强数据结构）
│   ├── embedding_manager.py   # Jina Embeddings v4管理
│   ├── vector_store.py        # FAISS向量存储（增强搜索）
│   ├── retriever.py          # 智能RAG检索（相邻块聚合）
│   ├── query_router.py       # 查询路由（强化Prompt）
│   ├── result_aggregator.py  # 结果聚合
│   └── api_client.py         # API客户端（优化超时）
├── API_KIT/                  # RESTful API服务模块
│   ├── api_server.py         # FastAPI服务器
│   ├── api_models.py         # API数据模型
│   ├── start_all.bat         # 一键启动脚本
│   ├── start_api.bat         # API启动脚本
│   ├── start_ngrok.bat       # ngrok启动脚本
│   ├── requirements_api.txt  # API依赖
│   └── README.md             # API详细文档
├── data/
│   ├── processed/            # 处理后的文档数据
│   └── vectors/              # FAISS向量索引
├── models/
│   └── jina-embeddings-v4/   # Jina嵌入模型
├── logs/                     # 系统日志
│   └── .gitkeep
├── docs/
│   └── INSTALL_FLASH_ATTENTION.md
├── .gitignore
├── main.py                   # 主程序入口
├── requirements.txt          # Python依赖
├── OPTIMIZATION_SUMMARY.md   # 优化总结报告
└── README.md                # 项目文档
```

## 🔧 核心优化技术

### 1. 智能分层检索架构

```python
# 根据查询复杂度动态调整检索策略
def smart_retrieve(self, query: str, max_context_chars: int = None):
    # 单省份查询：30个块，40000字符
    # 多省份查询：每省15个块，60000字符
    # 对比查询：每省25个块，100000字符
    # 通用查询：60个块，100000字符
```

### 2. 相邻块聚合机制

```python
def get_adjacent_chunks(self, chunk: DocumentChunk, window: int = 1):
    # 自动获取目标块的前后相邻块
    # 确保上下文的连续性和完整性
    # 提升信息检索的准确性
```

### 3. 优化截断策略

```python
def _truncate_results(self, result: RetrievalResult, max_chars: int):
    # 按信息密度评分排序
    # 优先保留高价值信息
    # 智能截断超长内容
```

### 4. 强化Prompt工程

```python
def _build_prompt(self, query: str, context: str, output_format: str):
    # 专业角色定位
    # 详细格式要求
    # 完整性验证机制
    # 量化数据优先
```

## 🙏 致谢

### 数据来源
感谢提供31省区市政府工作报告数据，让本项目能够开箱即用，为研究者和开发者提供便利。

### 开源贡献
欢迎提交Issue和Pull Request，共同完善这个项目：
- 🐛 报告Bug
- 💡 提出新功能建议  
- 📝 改进文档
- 🔧 代码优化

## 📈 性能监控

### 系统统计信息

系统启动时会显示详细统计：
```
📊 系统统计: 
- 总文档块数: 855
- 覆盖省份: 31
- 向量维度: 2048
- 各省份文档分布统计
```

### 查询性能指标

每次查询会显示：
- 检索块数
- 覆盖省份数
- 上下文字符数
- 处理时间
- 成功率

### 日志监控

```bash
# 查看系统日志
tail -f logs/government_rag.log

# 搜索性能信息
grep "检索完成\|处理时间" logs/government_rag.log
```

## 🛠️ 故障排除

### 常见问题

1. **API超时问题**
   - 已优化：API超时从60s增加到180s
   - 查询处理超时从30s增加到120s

2. **max_tokens限制**
   - 已修复：调整为模型支持的8192 tokens
   - 避免HTTP 400错误

3. **内存不足**
   ```bash
   # 检查可用内存
   python -c "import psutil; print(f'可用内存: {psutil.virtual_memory().available / 1024**3:.1f}GB')"
   ```

4. **模型加载失败**
   ```bash
   # 检查本地模型文件是否完整
   ls -la models/jina-embeddings-v4/models--jinaai--jina-embeddings-v4/snapshots/
   
   # 如果本地模型文件损坏或缺失，可以重新下载
   # 临时移除 local_files_only 参数进行下载
   python -c "
   from src.embedding_manager import JinaEmbeddingManager
   manager = JinaEmbeddingManager()
   manager.download_and_load_model()
   "
   ```

### 性能优化建议

1. **启用GPU加速**：确保CUDA环境正确配置
2. **内存管理**：建议32GB内存以获得最佳性能
3. **网络优化**：确保稳定的API网络连接
4. **定期维护**：清理日志文件和临时缓存

## 📋 依赖说明

主要依赖包：

```txt
python-docx==0.8.11      # Word文档解析
faiss-cpu==1.7.4         # 向量相似度搜索
transformers==4.36.2     # 预训练模型支持
torch==2.1.2             # 深度学习框架
numpy==1.24.3            # 数值计算
pandas==2.0.3            # 数据处理
requests==2.31.0         # HTTP请求
tqdm==4.66.1             # 进度条显示
scikit-learn==1.3.2      # 机器学习工具
jieba==0.42.1            # 中文分词
```

## 🔄 更新日志

### v2.0.0 (当前版本) 
- ✅ **重大优化**：实施阶段1无重切块优化方案
- ✅ **检索能力提升**：检索深度平均提升100%
- ✅ **上下文扩展**：支持100K字符长上下文
- ✅ **功能增强**：相邻块聚合、智能截断、强化Prompt
- ✅ **系统稳定性**：优化API超时、修复max_tokens限制
- ✅ **代码清理**：删除所有测试代码，保持生产环境整洁
- ✅ **文档完善**：更新README和优化总结报告
- ✅ **本地模型优化**：强制使用本地模型文件，避免网络下载，提升系统启动速度

### v1.0.0
- ✅ 基础RAG系统实现
- ✅ 31省政府工作报告支持
- ✅ 基本查询和检索功能

## 🎯 项目特色

本项目的核心价值在于：

1. **问题导向**：专门解决信息检索不完整和多省份对比数据不足的实际问题
2. **技术创新**：创新的智能分层检索架构和相邻块聚合机制
3. **性能优化**：通过系统性优化实现100%的信息量提升
4. **生产就绪**：清理了所有测试代码，适合生产环境部署
5. **文档完善**：详细的安装、使用和故障排除指南

## 📞 技术支持

如有问题或建议，请：
1. 查看本README文档的故障排除部分
2. 检查 `logs/government_rag.log` 日志文件
3. 参考 `OPTIMIZATION_SUMMARY.md` 优化报告
4. 提交Issue或联系开发团队

---

**🎉 系统已完成重大优化，实现了信息检索完整性和多省份对比数据详细度的显著提升！** 
