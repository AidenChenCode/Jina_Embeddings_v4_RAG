#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键安装并运行全部演示。

用法（在项目根目录）：
    python mvp/setup_and_run.py

它会自动：
  1. 检查 Python 版本
  2. 安装依赖（python-docx / numpy / scikit-learn / tqdm）
  3. 解压 31 省报告
  4. 修复 zip 内的 GBK 文件名
  5. 依次运行 4 个演示脚本

不需要 GPU，不需要下载 Jina 模型（7.5GB），不需要 API key。
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

# Windows 控制台默认不是 UTF-8，输出中文和 emoji 会报错
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MVP = ROOT / "mvp"
DOCS = ROOT / "docs"
ZIP = DOCS / "31省区市政府工作报告.zip"
DEPS = ["python-docx", "numpy", "scikit-learn", "tqdm"]

BAR = "=" * 68


def say(msg):
    print(f"\n{BAR}\n{msg}\n{BAR}")


def step_python():
    say("[1/5] 检查 Python 版本")
    v = sys.version_info
    print(f"  当前版本：Python {v.major}.{v.minor}.{v.micro}")
    print(f"  解释器路径：{sys.executable}")
    if (v.major, v.minor) < (3, 8):
        print("  ❌ 需要 Python 3.8 或更高版本")
        return False
    print("  ✅ 版本可用")
    return True


def step_deps():
    say("[2/5] 安装依赖")
    missing = []
    for pkg, mod in [("python-docx", "docx"), ("numpy", "numpy"),
                     ("scikit-learn", "sklearn"), ("tqdm", "tqdm")]:
        try:
            __import__(mod)
            print(f"  ✅ 已安装  {pkg}")
        except ImportError:
            print(f"  ⬇️  待安装  {pkg}")
            missing.append(pkg)

    if not missing:
        print("\n  依赖齐全，跳过安装")
        return True

    print(f"\n  正在安装 {len(missing)} 个包（可能需要一两分钟）...")
    cmd = [sys.executable, "-m", "pip", "install", "-q"] + missing
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("\n  ❌ 安装失败。可以试试手动运行：")
        print(f"     {sys.executable} -m pip install " + " ".join(missing))
        print("  如果提示权限问题，在命令末尾加 --user")
        return False

    for pkg, mod in [("python-docx", "docx"), ("numpy", "numpy"),
                     ("scikit-learn", "sklearn"), ("tqdm", "tqdm")]:
        try:
            __import__(mod)
        except ImportError:
            print(f"  ❌ {pkg} 安装后仍无法导入")
            return False
    print("  ✅ 全部安装完成")
    return True


def step_unzip():
    say("[3/5] 解压 31 省政府工作报告")
    if not ZIP.exists():
        print(f"  ❌ 找不到数据包：{ZIP}")
        print("     请确认你在项目根目录下运行，且 docs/ 里有那个 zip")
        return False

    existing = list(DOCS.glob("*.docx"))
    if len(existing) >= 31:
        print(f"  ✅ 已解压过（{len(existing)} 个 docx），跳过")
        return True

    with zipfile.ZipFile(ZIP) as z:
        z.extractall(DOCS)
        print(f"  ✅ 解压完成，共 {len(z.namelist())} 项")
    return True


def step_fix_names():
    say("[4/5] 修复文件名编码")
    print("  zip 内的文件名是 GBK 编码，直接解压会变成乱码。")
    print("  乱码会导致 data_processor 的省份识别（第一优先级）全部失效。\n")

    fixed, ok = 0, 0
    for f in list(DOCS.glob("*.docx")):
        name = f.name
        # 已经是正常中文就不动
        if any("一" <= ch <= "鿿" for ch in name):
            ok += 1
            continue
        try:
            good = name.encode("cp437").decode("gbk")
            target = DOCS / good
            if not target.exists():
                f.rename(target)
                fixed += 1
        except (UnicodeEncodeError, UnicodeDecodeError, OSError):
            pass

    total = len(list(DOCS.glob("*.docx")))
    print(f"  本次修复 {fixed} 个，原本正常 {ok} 个，当前共 {total} 个 docx")
    if total < 31:
        print(f"  ⚠️ 预期 31 个，实际 {total} 个")
    else:
        print("  ✅ 数据就绪")
        sample = sorted(DOCS.glob("*.docx"))[:3]
        for s in sample:
            print(f"     · {s.name}")
    return total > 0


def step_run():
    say("[5/5] 运行演示")
    scripts = [
        ("step1_chunking.py", "切块：31份报告 → 855个块"),
        ("walkthrough.py", "全流程：一个问题从提出到回答"),
        ("embedding_demo.py", "打分：Embedding 到底在做什么"),
        ("step2_retrieval.py", "验证：检索层的几个问题"),
    ]

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    results = []
    for i, (name, desc) in enumerate(scripts, 1):
        path = MVP / name
        if not path.exists():
            print(f"\n  ⚠️ 找不到 {name}，跳过")
            results.append((name, None))
            continue

        print(f"\n\n{'█' * 68}")
        print(f"█  演示 {i}/{len(scripts)}：{desc}")
        print(f"█  {name}")
        print(f"{'█' * 68}\n")

        r = subprocess.run([sys.executable, str(path)], env=env, cwd=str(ROOT))
        results.append((name, r.returncode == 0))

    return results


def main():
    print(f"\n{BAR}")
    print("  政府工作报告 RAG —— 演示环境一键搭建")
    print(f"  项目目录：{ROOT}")
    print(BAR)

    for fn in (step_python, step_deps, step_unzip, step_fix_names):
        if not fn():
            print("\n❌ 环境准备失败，已停止。请按上面的提示处理后重试。")
            return 1

    results = step_run()

    say("全部完成")
    for name, ok in results:
        mark = "✅" if ok else ("⚠️ 跳过" if ok is None else "❌ 出错")
        print(f"  {mark}  {name}")

    print("\n  想单独重跑某一个：")
    print(f"     {Path(sys.executable).name} mvp/walkthrough.py")
    print("\n  说明文档：mvp/README.md")
    return 0 if all(ok for _, ok in results if ok is not None) else 1


if __name__ == "__main__":
    sys.exit(main())
