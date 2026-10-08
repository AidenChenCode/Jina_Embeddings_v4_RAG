# 政府工作报告 RAG —— 容器镜像
#
# 两个构建目标（target），按需选一个：
#   demo —— 仅装 4 个轻量依赖，镜像约 400MB，构建 1~2 分钟。
#            TF-IDF 检索 + 仓库自带的 855 块数据，无需 GPU / 模型权重 / API Key。
#   full —— 装完整 requirements.txt（含 torch/transformers/faiss），镜像约 6GB。
#            模型权重和向量索引不打进镜像，通过卷挂载进来（见 docker-compose.yml）。
#
# 单独构建：
#   docker build --target demo -t govrag:demo .
#   docker build --target full -t govrag:full .
# 通常不用手敲，直接用 docker compose up -d demo

# ---------------------------------------------------------------- 公共基础层
FROM python:3.10-slim AS base

# 国内网络走清华源，海外服务器可删掉这两行（默认源更快）
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ---------------------------------------------------------------- demo 目标
FROM base AS demo

# 只装 demo 模式用得到的：TF-IDF 检索 + Web 服务
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        scikit-learn \
        numpy \
        requests

COPY . /app

EXPOSE 8000
# --demo 强制 demo 模式；0.0.0.0 才能被容器外访问（127.0.0.1 只能容器内自己看）
CMD ["python", "API_KIT/web_server.py", "--demo", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------- full 目标
FROM base AS full

# 编译 faiss / torch 相关扩展偶尔需要，装完即删以免镜像膨胀
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先只拷依赖清单再安装：改代码时这一层能命中缓存，不用重装 6GB 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir fastapi "uvicorn[standard]"

COPY . /app

EXPOSE 8000
# 不带 --demo：优先走完整系统，权重或索引缺失时 web_server.py 会自动降级 demo
CMD ["python", "API_KIT/web_server.py", "--host", "0.0.0.0", "--port", "8000"]
