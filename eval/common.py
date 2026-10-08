# -*- coding: utf-8 -*-
"""
评测共用的小工具。

刻意不 import 任何被测系统的代码（src/、API_KIT/、mvp/）：
评测集的标准答案和判分规则必须独立于被测系统，否则系统的 bug
会同时污染「答案」和「标准答案」，评测就失去了意义。
"""
import re

# 31 个省级行政区（不含港澳台），名称与语料中的 province 字段一致
PROVINCES = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
             "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
             "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆"]


def norm(s: str) -> str:
    """比对前统一格式：去掉所有空白，全角％转半角%（语料里两种都有）。"""
    return re.sub(r"\s+", "", s or "").replace("％", "%")


# 事实题的证据必须带上下文锚点。
# 反例：内蒙古报告开头有「预计地区生产总值增长6%左右」，说的是 2024 年预计值，
# 与 2025 年目标的文字完全相同。只比对数字或句子，会把错误年份的段落判成答对。
TARGET_ANCHOR = "预期目标"
ANCHOR_WINDOW = 40


def has_anchored(text_norm: str, evidence_norm: str) -> bool:
    """证据句出现，且其前 ANCHOR_WINDOW 字内有「预期目标」。两个参数都须先 norm()。"""
    start = 0
    while True:
        i = text_norm.find(evidence_norm, start)
        if i < 0:
            return False
        if TARGET_ANCHOR in text_norm[max(0, i - ANCHOR_WINDOW): i]:
            return True
        start = i + 1


# LLM 答案里表示「没有 / 不确定」的说法，用于识别拒答和过滤否定句
NEGATIONS = ("未提及", "没有提及", "未提到", "没有提到", "未涉及", "没有涉及", "未找到",
             "没有找到", "未发现", "没有发现", "未包含", "不包含", "并未", "无相关", "没有相关",
             "未见", "没有看到", "无法确定", "无法确认")


def segments(answer: str, fine: bool = False):
    """切句。粗粒度按换行和句末标点切（表格每行、列表每项各成一段），
    用于判断「省份和数字是否在同一句」；细粒度再按逗号、括号切，
    用于把「广东提到了，北京没有提到」这类句子里的肯定和否定分开。"""
    pattern = r"[\n。；;，,（）()]" if fine else r"[\n。；;]"
    return [s for s in re.split(pattern, answer or "") if s.strip()]


def is_negated(seg: str) -> bool:
    return any(n in seg for n in NEGATIONS)
