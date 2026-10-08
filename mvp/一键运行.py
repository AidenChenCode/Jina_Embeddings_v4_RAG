#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
放到桌面，双击运行（或在终端里 python 一键运行.py）。

它会自己完成所有事：
  · 在你的桌面建一个文件夹
  · 把项目下载进去
  · 装依赖、解压数据、修文件名
  · 把 4 个演示全部跑一遍

需要你电脑上有：Python 3.8+ 和 git
不需要：GPU、Jina 模型（7.5GB）、API key、conda
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/programming-thinker/Jina_Embeddings_v4_RAG.git"
BRANCH = "claude/project-purpose-e5ym2m"
FOLDER = "政府报告RAG演示"

# ---- Windows 控制台中文/emoji 支持 ----
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BAR = "=" * 66


def say(msg):
    print(f"\n{BAR}\n{msg}\n{BAR}")


def pause():
    """双击运行时窗口会秒关，停一下让人看清输出。"""
    try:
        input("\n按回车键关闭...")
    except (EOFError, KeyboardInterrupt):
        pass


def find_desktop() -> Path:
    """跨平台找桌面路径，兼顾 Windows 的 OneDrive 重定向。"""
    home = Path.home()
    candidates = []

    if sys.platform == "win32":
        # OneDrive 接管桌面的情况很常见，优先看它
        for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            p = os.environ.get(var)
            if p:
                candidates.append(Path(p) / "Desktop")
        up = os.environ.get("USERPROFILE")
        if up:
            candidates.append(Path(up) / "Desktop")
        candidates.append(home / "Desktop")
        candidates.append(home / "桌面")
    else:
        xdg = os.environ.get("XDG_DESKTOP_DIR")
        if xdg:
            candidates.append(Path(xdg))
        candidates.append(home / "Desktop")
        candidates.append(home / "桌面")

    for c in candidates:
        if c.is_dir():
            return c
    # 实在找不到桌面，就用主目录
    print(f"  ⚠️ 没找到桌面目录，改用主目录 {home}")
    return home


def have_git() -> bool:
    try:
        r = subprocess.run(["git", "--version"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            print(f"  ✅ {r.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return False


def main():
    print(f"\n{BAR}")
    print("  政府工作报告 RAG —— 一键演示")
    print(BAR)

    # ---- 1. 环境检查 ----
    say("[1/3] 检查环境")
    v = sys.version_info
    print(f"  ✅ Python {v.major}.{v.minor}.{v.micro}")
    if (v.major, v.minor) < (3, 8):
        print("  ❌ 需要 Python 3.8 以上版本")
        print("     去 https://www.python.org/downloads/ 装一个新的")
        return 1

    if not have_git():
        print("  ❌ 没有找到 git")
        print("\n  两个办法任选其一：")
        print("   (A) 装 git：https://git-scm.com/downloads")
        print(f"   (B) 手动下载：打开 {REPO[:-4]}")
        print(f"       切到分支 {BRANCH} → Code → Download ZIP")
        print("       解压后在项目目录里运行： python mvp/setup_and_run.py")
        return 1

    desktop = find_desktop()
    target = desktop / FOLDER
    print(f"  📁 桌面位置：{desktop}")
    print(f"  📁 将建立：  {target}")

    # ---- 2. 下载项目 ----
    say("[2/3] 下载项目")
    if (target / ".git").is_dir():
        print("  文件夹已存在，拉取最新代码...")
        r = subprocess.run(["git", "-C", str(target), "pull", "origin", BRANCH])
        if r.returncode != 0:
            print("  ⚠️ 更新失败，继续用现有代码")
    else:
        if target.exists() and any(target.iterdir()):
            print(f"  ❌ {target} 已存在且非空，但不是 git 仓库")
            print("     请改名或删掉它，然后重新运行")
            return 1
        print(f"  正在下载（约 3MB，第一次可能要等十几秒）...")
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "-b", BRANCH, REPO, str(target)]
        )
        if r.returncode != 0:
            print("\n  ❌ 下载失败。可能的原因：")
            print("     · 网络不通，或需要连 VPN")
            print("     · 仓库是私有的 —— 需要先配好 GitHub 账号权限")
            print(f"     · 手动下载：{REPO[:-4]}")
            return 1
        print("  ✅ 下载完成")

    # ---- 3. 交给项目自带的脚本 ----
    say("[3/3] 安装依赖并运行演示")
    runner = target / "mvp" / "setup_and_run.py"
    if not runner.exists():
        print(f"  ❌ 找不到 {runner}")
        return 1

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, str(runner)], cwd=str(target), env=env)

    say("结束")
    if r.returncode == 0:
        print(f"  ✅ 全部完成")
        print(f"\n  项目就在你桌面上：{target}")
        print(f"  说明文档：{FOLDER}/mvp/README.md")
        print(f"\n  想再单独看某一个演示，在项目目录里运行：")
        print(f"     python mvp/walkthrough.py      # 完整流程")
        print(f"     python mvp/embedding_demo.py   # 打分原理")
    else:
        print("  ⚠️ 运行过程中有步骤出错，往上翻看看具体报错")
    return r.returncode


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("\n已取消")
        code = 130
    except Exception as e:
        print(f"\n❌ 意外错误：{type(e).__name__}: {e}")
        code = 1
    pause()
    sys.exit(code)
