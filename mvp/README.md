# MVP 验证：检索层缺陷的量化复现

用**真实的 31 省报告数据**跑通切块与检索链路，量化验证代码审查中提出的假设。

## 为什么不用 Jina Embeddings

验证环境无 GPU、无模型权重（`models/` 在仓库中仅为空壳，权重被 `.gitignore` 排除）。
本 MVP 用 TF-IDF（char 2-3 gram）替代向量层。

**这不影响结论**：这里验证的缺陷都是流程性、逻辑性的——
"先取全局 top-N 再按省过滤" 的配额缺口、中文文本上 `.split()` 的失效、
两处意图识别规则不一致——都与向量质量无关。

**不能用本 MVP 验证的**：`prompt_name` 前缀错用（`vector_store.py:240` 用
默认的 `"passage"` 编码 query，而 Jina v4 是非对称模型）。该问题需要真实
Jina 权重才能量化，此处仅静态确认 `encode_query()` 从未被主链路调用。

## 运行

```bash
pip install python-docx numpy scikit-learn tqdm
cd docs && python -c "import zipfile; zipfile.ZipFile('31省区市政府工作报告.zip').extractall('.')"
# zip 内为 GBK 文件名，需修复（否则省份识别第一优先级失效）
python -c "
import os,glob
for f in glob.glob('docs/*.docx'):
    b=os.path.basename(f)
    try: os.rename(f, os.path.join('docs', b.encode('cp437').decode('gbk')))
    except: pass"

python mvp/step1_chunking.py    # 切块 + chunk_type 分布
python mvp/step2_retrieval.py   # 检索层三项缺陷
```

## 结果

数据：31 份报告 → **855 个块**，省份识别 31/31。

### ① `chunk_type == "title"` 永不产生 —— 已确认

| 类型 | 块数 | 占比 |
|---|---|---|
| target | 476 | 55.7% |
| content | 333 | 38.9% |
| summary | 46 | 5.4% |
| **title** | **0** | **0.0%** |

`data_processor.py:196` 判定 title 需 `len(text) < 100`，但实测**最短块 303 字符**
（中位 874）。切块粒度 1000 字与该判定条件互斥。

连带影响：`retrieve_by_topic(chunk_type="target")` 的过滤只筛掉 44% 的块。

### ② post-filter 的配额缺口 —— 部分确认，触发条件被修正

`retriever.py:196` 全省扫描，config 配额为每省 8 块 = **应得 248 块**：

| 查询 | 实得 | 缺口 |
|---|---|---|
| 各省2025年GDP增长目标 | 192 | 22.6% |
| 各省科技创新重点任务 | 185 | 25.4% |
| 各省民生保障举措 | 185 | 25.4% |
| 各省乡村振兴部署 | 178 | 28.2% |
| 各省绿色低碳目标 | 183 | 26.2% |

**平均缺口 26%**，但当前规模下**没有整省消失**——855 块时全局 top-200
已占全量 23%，足以触及每个省。

`vector_store.py:247` 的 `search_k` 硬编码为 200，缺口随索引规模恶化：

| 索引规模 | top-200 占比 | 实得/248 | 缺口 | 0块省份 |
|---|---|---|---|---|
| 855 | 23.4% | 192 | 22.6% | 0 |
| 2565 | 7.8% | 180 | 27.4% | 0 |
| 4275 | 4.7% | 176 | 29.0% | 0 |
| **8550** | **2.3%** | **154** | **37.9%** | **10** |

多年度报告入库后（10 年 ≈ 8550 块），**10 个省会整省查不到**。

### ③ `chunk_score` 对中文不做区分 —— 已确认

`retriever.py:487` `content_score = len(chunk.content.split()) / 100`：

- 中文无空格，实测取值 **0.02 ~ 0.15**
- 同式中 `char_score` 取值 **0 ~ 2.0**，相差两个数量级
- → `content_score` 对排序无实质贡献，截断退化为**纯按长度排序**

样本中数字最密集的块（甘肃，含 58 个数字）：

| 打分方式 | 排名 |
|---|---|
| 原版 `chunk_score` | 第 34 / 400 |
| 加数字密度后 | **第 1 / 400** |

README 声称的"含数字/量化指标的块加权"在代码中不存在。

### ④ 两处意图识别规则不一致 —— 已确认

`query_router.py:218`（elif 链）与 `retriever.py:131`（覆盖式）对同一 query
判定不同，**6 条测试中 3 条冲突**：

| 查询 | query_router | retriever | 实际生效预算 |
|---|---|---|---|
| 对比广东和江苏的产业发展 | multi_province | **comparison** | 25块/100K |
| 统计各省GDP增长目标 | all_provinces | **statistics** | topic检索 |
| 分析浙江和福建的数字经济 | multi_province | **statistics** | topic检索 |

实际生效的是 `retriever` 那一遍；`query_router` 的 `comparison` 分支因 elif
顺序（省份判断在前）**不可达**。

## 附带发现：三个部署阻断项

1. **zip 内文件名为 GBK 编码**，直接解压得到乱码文件名，
   `extract_province_from_filename`（第一优先级）全数失效
2. **`jieba` 全项目零调用**，但 `data_processor.py:18` 的 import 会阻断模块加载；
   而 `jieba==0.42.1` 在新版 setuptools 下构建失败
3. **模型权重不在仓库**，`local_files_only=True` 使缺失时直接报错退出
