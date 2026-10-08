# 云服务器部署教程

从零开始，把这个 RAG 问答系统部署到一台云服务器上，用 Docker 做环境隔离。

**面向没有运维经验的读者。** 每一步都会说清楚「为什么这么做」，而不只是给命令。

---

## 目录

- [开始之前：先想清楚要什么](#开始之前先想清楚要什么)
- [第一部分：开通云服务器](#第一部分开通云服务器)
- [第二部分：Docker 是什么，为什么要用](#第二部分docker-是什么为什么要用)
- [第三部分：两条部署路线](#第三部分两条部署路线)
- [第四部分：上线前必做的三件事](#第四部分上线前必做的三件事)
- [第五部分：成本控制与关机](#第五部分成本控制与关机)
- [附录 A：常见问题排查](#附录-a常见问题排查)
- [附录 B：升级到 GPU 服务器](#附录-b升级到-gpu-服务器)

---

## 开始之前：先想清楚要什么

这个项目有两种运行模式，**部署难度差一个数量级**，先确认你要哪个。

| | Demo 模式 | 完整模式 |
|---|---|---|
| 检索方式 | TF-IDF（关键词匹配） | Jina v4 语义向量 |
| 需要下载 | 无（数据已在仓库） | 7.5GB 模型权重 |
| 需要 GPU | 否 | 否（CPU 慢但能跑） |
| 服务器要求 | 1核2G 即可 | 2核8G 起步 |
| 部署耗时 | **3 分钟** | 1~2 小时（含下载和建索引） |
| 答案质量 | 检索原文摘编，或配 Key 后 LLM 生成 | 完整语义检索 + LLM 生成 |

**建议：先部署 Demo 模式。**

理由很实际——先用 3 分钟看到界面跑起来，确认服务器、端口、Docker 这一整条链路是通的，再去折腾 7.5GB 的权重。否则一旦出问题，你分不清是网络问题、端口问题还是模型问题。

> 如果只是面试演示，**Demo 模式配上 API Key 就完全够用了**：检索用 TF-IDF，答案由 LLM 生成，界面和交互与完整模式完全一致。

---

## 第一部分：开通云服务器

### 1.1 选哪种服务器

以阿里云为例（腾讯云、华为云的概念完全一样，只是叫法不同）：

| 产品 | 说明 | 建议 |
|---|---|---|
| **轻量应用服务器** | 打包了固定带宽和流量，界面简单，新人友好 | ✅ **推荐** |
| ECS 云服务器 | 配置灵活，但选项多、容易选错、计费项分散 | 熟悉后再用 |

**配置怎么选：**

| 用途 | 配置 | 大致价格 |
|---|---|---|
| 只跑 Demo 模式 | 2核2G / 2核4G | ¥60~100 / 月 |
| 跑完整模式 | **2核8G**（内存是硬要求） | ¥150~300 / 月 |

**为什么完整模式要 8G 内存？** Jina v4 模型加载进内存就要好几个 G，加上 FAISS 索引和 Python 运行时，4G 会直接 OOM（内存溢出被系统杀掉）。这是最容易踩的坑——服务莫名其妙就没了，日志里只有一句 `Killed`。

**磁盘至少 40G**：模型权重 7.5G + Docker 镜像 6G + 系统本身，20G 会很紧张。

### 1.2 购买时的三个关键选择

**① 地域：选华东（上海/杭州）或华北（北京）**

不要选香港或海外节点。虽然那边不用备案，但后面装 Docker、拉镜像、下载模型时，国内镜像源的加速对海外节点无效，会慢到怀疑人生。

**② 镜像（操作系统）：Ubuntu 22.04 LTS**

不要选 CentOS（已停止维护）。有些云厂商提供「Docker 应用镜像」，选了可以省掉装 Docker 的步骤，但不选也没关系，第二部分有安装命令。

**③ 计费方式**

- **包月**：便宜，适合要长期用
- **按量付费**：用几小时算几小时，适合「面试前开一天，演示完就释放」

> 💡 如果只为面试演示，按量付费 + 用完立即释放，总花费可能不到 10 块钱。

### 1.3 ⚠️ 放行端口（新手最容易卡在这里）

**服务器买好后第一件事就是这个。** 90% 的「服务明明起来了但浏览器打不开」都是这个原因。

云服务器默认只开放 22 端口（SSH 登录用），你的应用跑在 8000 端口，**必须手动放行**，否则外网访问不到。

**操作路径：**

- 阿里云轻量服务器：控制台 → 你的实例 → **防火墙** → 添加规则
- 阿里云 ECS：控制台 → 实例 → 安全组 → 配置规则 → 入方向 → 手动添加
- 腾讯云：控制台 → 实例 → 防火墙 / 安全组

**要添加的规则：**

| 应用类型 | 端口 | 源地址 | 用途 |
|---|---|---|---|
| SSH | 22 | 0.0.0.0/0 | 登录服务器（通常默认已开） |
| 自定义 TCP | **8000** | 0.0.0.0/0 | 访问问答界面 |

> `0.0.0.0/0` 表示允许任何 IP 访问。如果只想自己用，可以填你家里的公网 IP（百度搜「我的IP」能查到），更安全。

### 1.4 连上服务器

在控制台记下你的**公网 IP**（形如 `47.101.xx.xx`）。

**Mac / Linux** —— 打开终端：

```bash
ssh root@你的公网IP
# 首次连接会问 yes/no，输入 yes，然后输入购买时设置的密码
```

**Windows** —— 打开 PowerShell（开始菜单搜索）：

```powershell
ssh root@你的公网IP
```

> Windows 10/11 自带 ssh 命令。如果提示找不到，可以下载 [Xshell](https://www.xshell.com/zh/free-for-home-school/)（个人免费）或 [PuTTY](https://www.putty.org/)。

**看到类似这样的提示符就成功了：**

```
root@iZbp1xxxxxxZ:~#
```

> 🔐 **关于密钥登录**：正式环境建议改用 SSH 密钥而非密码——密码可以被暴力破解，公网服务器每天都会被扫。个人练手用密码可以，但**密码一定要复杂**。云厂商控制台都有「密钥对」功能，几分钟能配好。

---

## 第二部分：Docker 是什么，为什么要用

### 2.1 用集装箱理解 Docker

在集装箱发明之前，货物装船要一件件搬，不同形状的货物互相挤压。集装箱统一了尺寸，**里面装什么船都不用管**，直接吊装。

Docker 做的是同一件事：把「应用 + 它需要的所有依赖」打包成一个标准盒子，服务器不用关心里面装了什么。

**三个概念，用这个项目来对应：**

| 概念 | 是什么 | 在本项目里 |
|---|---|---|
| **镜像**（Image） | 打包好的只读模板，像是「装好了所有软件的系统快照」 | `govrag:demo` —— 装好了 Python + fastapi + scikit-learn |
| **容器**（Container） | 镜像跑起来的实例，像是「按快照开出来的一台虚拟机」 | `govrag-demo` —— 正在 8000 端口提供服务的那个进程 |
| **卷**（Volume） | 挂载进容器的宿主机目录，容器删了数据还在 | `./models`（7.5GB 权重）、`./data`（向量索引） |

**关键理解：容器是「用完即弃」的，卷是「要保留」的。**

这就是为什么模型权重不打进镜像，而是挂载——镜像每次改代码都要重建，7.5GB 跟着重建一遍是灾难；挂载的话，容器删一百次，权重还在宿主机上。

### 2.2 这个项目为什么特别需要 Docker

**因为依赖版本极其敏感。**

`torch` / `transformers` / `faiss` 这三个库的版本必须互相匹配，装错一个版本就会出现各种诡异报错。而且：

- 直接装在服务器上，一旦装错，**卸载不干净**，残留的旧版本会继续捣乱
- 你在自己电脑上装的和服务器上装的可能不一样，出现「我这儿明明是好的」
- 想同时试两个版本？没办法，全局只能有一份

用 Docker 之后：

```bash
docker compose down          # 整个环境删掉
docker compose up -d demo    # 3 分钟重来一个干净的
```

**这就是「隔离」的真正价值** —— 不是为了炫技，是为了让你能随便折腾、随时重来。

### 2.3 安装 Docker

在服务器上依次执行：

```bash
# 1. 安装 Docker（官方脚本，国内走阿里云镜像加速）
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 2. 设置开机自启
systemctl enable docker && systemctl start docker

# 3. 验证
docker --version
docker compose version
```

看到版本号就成功了。

**配置镜像加速器（国内服务器必做）：**

不配的话拉镜像会卡在 0%，因为 Docker 官方仓库在国外。

```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://mirror.baidubce.com"
  ]
}
EOF

systemctl daemon-reload && systemctl restart docker
```

> 镜像加速地址会失效，如果全部拉不动，搜索「docker 镜像加速 2026」找最新可用的。阿里云用户还可以在控制台「容器镜像服务」里领取专属加速地址（更稳定）。

---

## 第三部分：两条部署路线

### 3.1 把代码放上服务器

```bash
# 装 git（Ubuntu 一般自带，没有就装）
apt update && apt install -y git

# 克隆仓库（注意 -b 后面的分支名，不能省）
git clone -b claude/project-purpose-e5ym2m https://github.com/AidenChenCode/Jina_Embeddings_v4_RAG.git
cd Jina_Embeddings_v4_RAG
```

> ⚠️ **为什么必须带 `-b 分支名`？** 网页前端、Demo 后端、Docker 配置、Demo 数据（`mvp/chunks.json`）都只在 `claude/project-purpose-e5ym2m` 分支上，**没有合并进 `main`**。`git clone` 默认拿的是 `main`，不带 `-b` 的话，后面 `docker compose up -d demo` 会直接报找不到文件。
>
> 已经 clone 过 `main` 的，切过去即可：
> ```bash
> git fetch origin && git checkout claude/project-purpose-e5ym2m
> ```
>
> 验证拿对了：`ls docker-compose.yml web/index.html` 两个文件都在就没问题。

> 如果仓库是私有的，`git clone` 会要求输入账号密码。GitHub 现在不支持密码了，需要用 [Personal Access Token](https://github.com/settings/tokens)。或者简单粗暴：本地打包好用 `scp` 传上去。

---

### 3.2 路线 A：Demo 模式（推荐先做这个）

**一条命令：**

```bash
docker compose up -d demo
```

首次运行会构建镜像（拉 Python 基础镜像 + 装 4 个依赖），**约 2~3 分钟**。

`-d` 表示后台运行（detached），不加的话日志会占住你的终端，关掉 SSH 服务就停了。

**验证：**

```bash
# 1. 看容器是否在运行
docker compose ps
# STATUS 列应该显示 Up

# 2. 在服务器本地测一下接口
curl http://127.0.0.1:8000/api/health
# 应返回：{"status":"ok","mode":"demo"}

# 3. 看日志
docker compose logs demo
# 应看到：DemoRAG 就绪: 855 块 / 31 省
```

**然后打开浏览器：**

```
http://你的公网IP:8000
```

应该看到问答界面，顶栏显示 **「Demo · TF-IDF 摘编」** 和 **「855 块 · 31 省」**。点一个示例问题试试。

> ❌ **打不开？** 99% 是端口没放行，回到 [1.3 节](#13-️放行端口新手最容易卡在这里)。注意是 `http://` 不是 `https://`，也别漏了 `:8000`。

**让答案由 LLM 生成（可选但强烈建议）：**

Demo 模式默认返回检索到的原文摘编。配上 API Key 后，答案质量立刻接近完整模式：

```bash
# 1. 到 https://siliconflow.cn 注册，控制台创建 API Key（新用户有免费额度）
# 2. 写进环境变量文件
echo 'SILICONFLOW_API_KEY=你的key' > .env

# 3. 重启使其生效
docker compose up -d demo
```

刷新页面，顶栏会变成 **「Demo · TF-IDF + LLM」**。

> `.env` 文件已被 `.gitignore` 排除，不会误传到 GitHub。**永远不要把 API Key 提交进仓库**——GitHub 上有机器人专门扫这个，泄露后几分钟内就会被盗刷。

---

### 3.3 路线 B：完整模式

先确认路线 A 已经跑通，再做这个。

**① 下载模型权重（7.5GB，只需一次）**

在**宿主机**上下载，不是在容器里——这样容器删了重建也不用重下。

```bash
# 装下载工具
pip install -U huggingface_hub

# 走国内镜像（不设置的话基本下不动）
export HF_ENDPOINT=https://hf-mirror.com

# 下载到项目的 models 目录
hf download jinaai/jina-embeddings-v4 --local-dir models/jina-embeddings-v4
```

耗时取决于带宽，几十分钟到几小时。

> 💡 **断了怎么办？** 重新执行同样的命令即可，会自动断点续传，已下载的文件不会重来。
>
> 💡 建议用 `screen` 或 `tmux` 跑，避免 SSH 断开导致下载中断：
> ```bash
> apt install -y screen
> screen -S download
> # 在里面执行下载命令，然后按 Ctrl+A 再按 D 退出
> # 想看进度：screen -r download
> ```

**验证下载完整：**

```bash
ls models/jina-embeddings-v4/config.json && echo "✅ 权重就绪"
```

**② 配置 API Key**

```bash
echo 'SILICONFLOW_API_KEY=你的key' > .env
```

**③ 启动完整模式容器**

```bash
docker compose down            # 先停掉 demo（避免抢 8000 端口）
docker compose up -d full      # 首次构建约 10~20 分钟（要装 torch 等大依赖）
```

**④ 构建向量索引（首次必做）**

```bash
docker compose exec full python setup_full.py
```

这个脚本会自动逐项检查：依赖 → 配置文件 → 模型权重 → 建索引，缺什么会打印精确的解决命令。

建索引 CPU 上约 **15~40 分钟**（855 个文本块逐个编码）。**只需做一次**，索引存在挂载的 `./data` 目录里，之后重启容器直接复用。

**⑤ 重启并验证**

```bash
docker compose restart full
docker compose logs -f full     # Ctrl+C 退出日志查看
```

刷新浏览器，顶栏显示 **「完整系统 · Jina v4」** 就成功了。提问后展开「引用来源」，能看到真实的语义相似度分数。

> ⚠️ 如果顶栏仍显示 Demo，说明完整系统初始化失败自动降级了。`docker compose logs full` 里会有具体原因——通常是权重路径不对或内存不足。

---

## 第四部分：上线前必做的三件事

### 4.1 加一层访问控制（重要）

**现在的服务是完全裸露的**：任何知道你 IP 的人都能打开界面、调用接口、**烧你的硅基流动 API 额度**。公网 IP 每天都会被扫描器扫到。

**最省事的方案** —— 防火墙只放行你自己的 IP：

回到 [1.3 节](#13-️放行端口新手最容易卡在这里)的防火墙规则，把 8000 端口的源地址从 `0.0.0.0/0` 改成你的公网 IP（百度搜「我的IP」）。

代价是换网络（比如从家里到公司）就要改一次。**但对个人演示场景，这是性价比最高的做法。**

**需要给别人访问时** —— 加 nginx 密码保护：

```bash
apt install -y nginx apache2-utils

# 创建用户名密码（会提示输入密码）
htpasswd -c /etc/nginx/.htpasswd admin

# 配置反向代理
cat > /etc/nginx/sites-available/govrag <<'EOF'
server {
    listen 80;
    location / {
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 200s;   # LLM 生成慢，超时要放宽
    }
}
EOF

ln -sf /etc/nginx/sites-available/govrag /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

然后防火墙放行 **80** 端口、**关掉 8000** 的对外放行。访问 `http://你的IP` 时会要求输入用户名密码。

> `proxy_read_timeout 200s` 这行不能少。默认 60 秒，而完整模式下 LLM 生成长答案可能要 90 秒以上，不改会看到 504 错误。

### 4.2 不要开多 worker

你可能在别的教程里看到 `uvicorn --workers 4` 能提高并发。**这个项目不要这么做。**

原因：完整模式下每个 worker 进程会**独立加载一份 7.5GB 的模型**。4 个 worker ≈ 30GB 内存起步，而且它们各自持有互不相通的索引实例，初始化接口只会命中其中一个。

`docker-compose.yml` 里已经刻意不暴露 workers 参数。研究场景的并发量，单进程完全够用。

### 4.3 保活与日常运维

`docker-compose.yml` 里已配置 `restart: unless-stopped`，意思是：

- 容器崩溃 → 自动重启 ✅
- 服务器重启 → 自动拉起 ✅
- 你手动 `docker compose down` → 不会自己起来 ✅（符合预期）

**日常命令速查：**

```bash
docker compose ps               # 看运行状态
docker compose logs -f demo     # 实时日志（Ctrl+C 退出）
docker compose restart demo     # 重启
docker compose down             # 停止并删除容器（卷里的数据不受影响）

# 更新代码后
git pull
docker compose restart demo     # 代码是挂载进去的，改完重启即可
docker compose up -d --build demo   # 如果改了依赖，才需要重新 build
```

---

## 第五部分：成本控制与关机

### 5.1 花在哪里

| 项目 | 计费方式 | 大致金额 |
|---|---|---|
| 云服务器 | 包月 / 按量 | ¥60~300 / 月 |
| 公网流量 | 轻量服务器含固定流量包 | 通常够用 |
| 硅基流动 API | 按 token 用量 | 新用户有免费额度；重度使用几十元/月 |
| 模型权重存储 | 占磁盘，不额外收费 | — |

### 5.2 ⚠️ 不用的时候记得处理

**这是最容易忘、也最容易造成损失的一步。**

| 操作 | 是否继续扣费 | 数据是否保留 | 适用场景 |
|---|---|---|---|
| `docker compose down` | ✅ 服务器还在扣 | 保留 | 只是暂停服务 |
| 控制台「**关机**」 | 轻量服务器仍扣；ECS 按量可能停止计费 | 保留 | 短期不用 |
| 控制台「**释放/退订**」 | ❌ 不再扣费 | **全部删除** | 确定不用了 |

**面试演示的建议流程：**

1. 面试前一天开机，完整跑一遍确认没问题（**不要当天才第一次试**）
2. 面试当天提前 30 分钟打开页面确认服务正常
3. 演示结束后，如果短期不用了 → **释放实例**

> 💡 释放前如果想留个底，把 `data/` 目录（向量索引）打包下载到本地，下次重建可以省掉 40 分钟：
> ```bash
> tar czf index-backup.tar.gz data/
> # 然后在自己电脑上：scp root@你的IP:~/Jina_Embeddings_v4_RAG/index-backup.tar.gz .
> ```

---

## 附录 A：常见问题排查

### `docker compose up` 报 "no configuration file provided" / 找不到文件

**clone 时没带分支名，拿到的是 `main`。** 本项目的部署文件只在 `claude/project-purpose-e5ym2m` 分支上：

```bash
git fetch origin && git checkout claude/project-purpose-e5ym2m
ls docker-compose.yml web/index.html     # 两个都在才对
```

### 浏览器打不开页面

按顺序排查：

```bash
# ① 容器在跑吗？
docker compose ps          # STATUS 应为 Up，不是 Exited

# ② 服务器本地能通吗？
curl http://127.0.0.1:8000/api/health
```

- **本地 curl 通了，浏览器不通** → **端口没放行**，回 [1.3 节](#13-️放行端口新手最容易卡在这里)。这是最常见的原因
- **本地 curl 也不通** → 看 `docker compose logs demo` 里的报错
- 检查 URL：必须是 `http://` 不是 `https://`，且不能漏 `:8000`

### 拉镜像卡住 / 超时

镜像加速器没配或已失效，回 [2.3 节](#23-安装-docker)重新配置。搜索「docker 镜像加速 2026」找当前可用地址。

### 容器启动后立刻退出（Exited）

```bash
docker compose logs demo    # 看最后几行的报错
```

常见原因：
- **端口被占用** → `lsof -i:8000` 查什么在占，或改 compose 里的端口映射为 `"9000:8000"`
- **8000 端口同时起了 demo 和 full** → 先 `docker compose down` 再启一个

### 日志里出现 `Killed` / 容器莫名重启

**内存不足（OOM）。** 完整模式至少要 8G 内存。

```bash
free -h              # 看可用内存
```

临时缓解：加 swap（性能会下降，但能救急）

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

根本解决：升级服务器配置，或退回 Demo 模式。

### 模型下载中断

重新执行同样的 `hf download` 命令即可断点续传。用 `screen` 跑可避免 SSH 断开导致中断。

### 顶栏一直显示 Demo，切不到完整模式

```bash
docker compose logs full | grep -i "降级\|失败\|error"
```

依次确认：
1. `ls models/jina-embeddings-v4/config.json` 存在吗
2. `ls data/vectors/faiss_index.bin` 存在吗（不存在说明索引没建，跑 `setup_full.py`）
3. 内存够吗（`free -h`）

### 磁盘满了

```bash
df -h                        # 看使用率
docker system prune -a       # 清理无用的镜像和缓存（可释放几个 G）
```

---

## 附录 B：升级到 GPU 服务器

CPU 完全能跑，只是慢。如果确实需要 GPU（比如要频繁重建索引，或查询量大）：

**① 买 GPU 实例**：阿里云 `ecs.gn7i`（A10 卡，24GB 显存）或同级产品，按小时计费，价格以控制台为准。**用完一定要释放**，忘记关是烧钱最快的方式。

> ⚠️ **不要选 T4（`gn6i`）、V100 这类老卡。** 代码用 bfloat16 精度加载模型（`src/embedding_manager.py`），bf16 要 Ampere 架构及以上的显卡（A10、A100、30 系、40 系）才有硬件支持，老卡上会报错或慢得多。
>
> 购买时：镜像选 **Ubuntu 22.04**（自带 Python 3.10；`requirements.txt` 钉死的 numpy 1.24.3 不支持 Python 3.12，所以别选 24.04），并勾选**自动安装 GPU 驱动**。

**② 装 NVIDIA 驱动**（通常选带驱动的镜像可跳过）：

```bash
nvidia-smi    # 能看到显卡信息就说明驱动 OK
```

**③ 装 NVIDIA Container Toolkit**（让容器能用显卡）：

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt update && apt install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
```

**④ 给 compose 的 `full` 服务加上 GPU 声明**：

```yaml
  full:
    # ... 其余配置不变 ...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

**⑤ 首次部署跑 `setup_full.py`**（自动解压报告、生成配置、检测到 GPU、建索引）：

```bash
docker compose up -d full
docker compose exec full python setup_full.py
docker compose restart full
```

已经在 CPU 上建过索引的，换到 GPU 不用重建——索引和用什么设备算出来的无关。

**效果对比：**

| | CPU | GPU (A10) |
|---|---|---|
| 建索引（855 块） | 15~40 分钟 | 2~5 分钟 |
| 单次查询编码 | 1~3 秒 | 毫秒级 |

注意：**生成答案的时间不变**（那部分调的是硅基流动的 API，不在你的服务器上跑）。所以对最终响应时间的改善，没有你想象的那么大。

---

## 一页速查

```bash
# ===== 首次部署（Demo 模式）=====
ssh root@你的公网IP
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
git clone -b claude/project-purpose-e5ym2m https://github.com/AidenChenCode/Jina_Embeddings_v4_RAG.git
cd Jina_Embeddings_v4_RAG
echo 'SILICONFLOW_API_KEY=你的key' > .env      # 可选
docker compose up -d demo
# 浏览器打开 http://你的公网IP:8000

# ===== 日常运维 =====
docker compose ps                  # 状态
docker compose logs -f demo        # 日志
docker compose restart demo        # 重启
docker compose down                # 停止

# ===== 升级到完整模式 =====
export HF_ENDPOINT=https://hf-mirror.com
hf download jinaai/jina-embeddings-v4 --local-dir models/jina-embeddings-v4
docker compose down && docker compose up -d full
docker compose exec full python setup_full.py
```

**记住四件事：**

1. **clone 要带分支名** —— `-b claude/project-purpose-e5ym2m`，`main` 上没有部署文件
2. **先跑 Demo 模式** —— 3 分钟看到结果，链路通了再折腾权重
3. **端口一定要放行** —— 打不开页面基本都是这个原因
4. **用完记得释放** —— 按量计费忘记关是最常见的损失
