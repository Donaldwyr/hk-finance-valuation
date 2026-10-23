# -*- coding: utf-8 -*-
"""
港股财报 PE / PB / PS 解析估值工具（Gradio 演示版）
====================================================

功能：
  1. 上传文字版（text-based）PDF 财报
  2. 调用 DeepSeek API 提取：营业收入、归母净利润、净资产、总股本（另提取人民币面值股本，仅参考）
  3. 自动识别港股财报常见单位（HK$ million / 百万、千元 / HK$ thousand、亿元；百万股 / 亿股 / 万股 / 股），统一换算为「港元 / 股」
  4. 严格「先判断、再除法」，绝不输出负数估值：
       - 归母净利润 > 0 才计算 PE，否则 PE = None
       - 净资产      > 0 才计算 PB，否则 PB = None
       - 营业收入    > 0 才计算 PS，否则 PS = None
  5. 结果表格展示 + plotly 绘图
  6. 支持导出 Excel / Markdown 备忘
  7. try/except 捕获 PDF 读取、API 调用异常并友好提示
  8. 从本地 .env 读取 DEEPSEEK_API_KEY（绝不硬编码密钥）

使用：
  pip install -r requirements.txt
  cp .env.example .env     # 填入真实 DeepSeek API Key
  python app.py
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime

import gradio as gr
import pandas as pd
import pdfplumber
import plotly.graph_objects as go
from dotenv import load_dotenv

# ------------------------------ 配置 ------------------------------
load_dotenv()                                    # 读取当前目录 .env
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")  # 只从环境读取，绝不硬编码
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
OUTPUT_DIR = "outputs"       # 导出文件目录
MAX_TEXT_CHARS = 30000       # 送入模型的财报文本上限（防超 token）

# ------------------------- 单位识别与换算 -------------------------
# 金额单位 -> 换算到「港元」的系数。
# 港股财报常见单位规则：
#   HK$ million / 百万   = ×1,000,000
#   千元 / HK$ thousand  = ×1,000
#   亿元                  = ×100,000,000
# 注意：列表按「从长/大到短/小」排列，避免「百万」被「万」、「十亿」被「亿」误匹配。
CURRENCY_FACTORS = [
    ("十亿", 1e9),
    ("亿", 1e8),
    ("百万", 1e6),
    ("million", 1e6),      # HK$ million
    ("万", 1e4),
    ("千", 1e3),
    ("thousand", 1e3),     # HK$ thousand
    ("港元", 1.0),         # 已是港元基准
    ("港币", 1.0),
    ("hkd", 1.0),
    ("hk$", 1.0),
]
# 股本单位 -> 换算到「股」的系数
# 注意：按「从大到小」排列，「百万股」必须在「万股」之前，否则「百万股」会被误匹配成「万股」。
SHARE_FACTORS = [("亿股", 1e8), ("百万股", 1e6), ("万股", 1e4), ("股", 1.0)]


def to_float(x):
    """安全转 float；空值/None/非法值统一返回 None。"""
    if x is None or x == "":
        return None
    if isinstance(x, str):
        # 去掉千分位逗号（含中文逗号），避免「1,234.5」被误判为非法
        x = x.strip().replace(",", "").replace("，", "")
    if x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def match_factor(unit, factors):
    """在单位字符串中模糊匹配已知单位，返回换算系数；无法识别返回 None。"""
    if unit is None:
        return None
    u = str(unit).strip().lower().replace(" ", "").replace(",", "")
    if not u:
        return None
    for token, factor in factors:
        if token in u:
            return factor
    return None


def convert_to_base(value, unit, kind="currency"):
    """数值+单位 -> 统一基准（港元 / 股），带 unit_unknown 兜底。

    返回 dict：
        value        : 换算后的数值（None 表示无法计算）
        unit_unknown : 单位是否识别不出（True 时不强行计算）
        raw_value    : 模型返回的原始数值
        raw_unit     : 模型返回的原始单位
    识别不出单位时不抛异常，打印警告并标记 unit_unknown。"""
    v = to_float(value)
    base_label = "港元" if kind == "currency" else "股"
    if v is None:
        # 数值缺失（模型填 null / 非法值）
        print(f"[日志] 数值缺失（原始值={value!r}，单位={unit!r}）-> 跳过，不计算")
        return {"value": None, "unit_unknown": False,
                "raw_value": value, "raw_unit": unit}
    factors = SHARE_FACTORS if kind == "shares" else CURRENCY_FACTORS
    factor = match_factor(unit, factors)
    if factor is None:
        # 兜底：单位识别不出 -> 返回警告，不强行计算
        print(f"[警告 unit_unknown] 单位「{unit}」无法识别，跳过计算（基准={base_label}）")
        return {"value": None, "unit_unknown": True,
                "raw_value": value, "raw_unit": unit}
    converted = v * factor
    print(f"[日志] 原始值={value}，原始单位={unit!r}，"
          f"换算系数={factor:.0f}，换算后={converted:,.2f} {base_label}")
    return {"value": converted, "unit_unknown": False,
            "raw_value": value, "raw_unit": unit}


def extract_field(raw, name):
    """从模型 JSON 里安全取出某字段的「原始数值」和「原始单位」。

    兼容两种情况：
      1. 标准结构   {"数值": 123.45, "单位": "百万"}
      2. 模型漏掉单位、只返回裸数字 123.45 -> 单位记为 None，
         交给 convert_to_base 标记 unit_unknown（不强行计算）。
    字段缺失时返回 (None, None)。"""
    field = raw.get(name)
    if isinstance(field, dict):
        return field.get("数值"), field.get("单位")
    if field is None:
        return None, None
    # 裸数字 / 裸字符串：只有数值、没有单位
    return field, None

# ------------------------- PDF 文字提取 -------------------------
def extract_pdf_text(pdf_path):
    """用 pdfplumber 抽取文字；扫描版/无文字层时友好提示。"""
    if not pdf_path:
        raise ValueError("请先上传 PDF 财报文件")
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
    full = "\n".join(parts).strip()
    if not full:
        raise ValueError("未能提取到文字：可能是扫描版/图片型 PDF，请上传文字版（text-based）PDF")
    return full


# ------------------------- DeepSeek 调用 -------------------------
SYSTEM_PROMPT = (
    "你是专业的港股上市公司财报数据提取助手。"
    "只能从用户提供的财报文本中提取数据，严禁编造或猜测，找不到的字段数值填 null。"
    "每个金额/股本字段必须同时返回「数值」和「单位」两个键（原始数值 + 原始单位），"
    "严禁只返回裸数字；单位必须照抄财报原文，识别不清就照抄原文。"
    "「总股本」是已发行总股数（股数口径），「股本面值」是人民币计价的面值金额，两者必须分开提取、分别标注单位，严禁混淆。"
    "严格输出 JSON，不要输出 JSON 以外的任何文字。"
)


def build_extraction_prompt(text):
    snippet = text[:MAX_TEXT_CHARS]
    return (
        "请从下面这份港股财报文本中提取以下字段（合并报表口径，优先取报告期最新一期）：\n"
        "1. 报告期（如「截至2024年12月31日止年度」）\n"
        "2. 币种（人民币 / 港元 / 美元，仅为参考）\n"
        "3. 营业收入（必须同时返回【原始数值】和【原始单位】）\n"
        "4. 归母净利润（归属于母公司股东的净利润，必须同时返回【原始数值】和【原始单位】）\n"
        "5. 净资产（归属于母公司股东的净资产 / 股东权益，必须同时返回【原始数值】和【原始单位】）\n"
        "6. 总股本（已发行总股数，股数口径，不是面值/金额。单位务必区分：百万股 / 亿股 / 万股 / 股，"
        "必须同时返回【原始数值】和【原始单位】。提示：腾讯等公司年报常把总股数写在「财务附注」「股本变动表/权益变动表」里，"
        "不在利润表或资产负债表主表，务必去这些位置查找并提取）\n"
        "7. 股本面值（人民币面值口径，如有）：原文若披露以人民币计价的股本面值（例如「股本 9.5亿元」），"
        "单独提取并标注单位，仅作参考，严禁与第 6 项总股本（股数）混淆；找不到则数值填 null、单位填 null）\n\n"
        "【原始单位】必须如实照抄财报里的写法，例如：HK$ million、HK$ thousand、百万、千元、亿元、万、港元、"
        "百万股、亿股、万股、股。\n"
        "严禁只返回裸数字：每个金额/股本字段都必须带「数值」和「单位」两个键；单位识别不清就照抄原文，不要自己改写。\n"
        "找不到的字段数值填 null、单位填 null。\n\n"
        "严格按以下 JSON 结构输出（仅输出 JSON，不要任何多余文字）：\n"
        '{"报告期":"...","币种":"...",'
        '"营业收入":{"数值":123.45,"单位":"百万"},'
        '"归母净利润":{"数值":12.34,"单位":"HK$ million"},'
        '"净资产":{"数值":100.0,"单位":"亿元"},'
        '"总股本":{"数值":50.0,"单位":"亿股"},'
        '"股本面值":{"数值":9.5,"单位":"亿元"}}\n\n'
        "财报文本：\n" + snippet
    )


def call_deepseek(text):
    """调用 DeepSeek chat/completions，返回模型输出的字符串（应为 JSON）。"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("未读取到 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填入真实 Key")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_extraction_prompt(text)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"DeepSeek API 返回错误（HTTP {e.code}）：{body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 DeepSeek API（{e.reason}），请检查网络") from e
    except TimeoutError:
        raise RuntimeError("DeepSeek API 请求超时，请重试") from None
    return data["choices"][0]["message"]["content"]


def parse_model_output(content):
    """把模型输出解析成 dict，兼容 ```json 代码块包裹。"""
    c = (content or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", c, re.S)
    if m:
        c = m.group(1).strip()
    try:
        return json.loads(c)
    except json.JSONDecodeError:
        start, end = c.find("{"), c.rfind("}")
        if start != -1 and end > start:
            return json.loads(c[start:end + 1])
        raise ValueError("DeepSeek 返回内容不是合法 JSON，请重试")

# ------------------------- 估值计算 -------------------------
def compute_valuations(revenue, net_profit, equity, shares, price):
    """核心：先判断、再除法，绝不输出负数估值。
    revenue/net_profit/equity=港元；shares=股；price=港元/股。
    总市值 = 股价 × 总股本（仅当股价>0 且股本>0 时成立）。"""
    market_cap = None
    if price is not None and shares is not None and price > 0 and shares > 0:
        market_cap = price * shares

    def ratio(numerator, denominator):
        """分子、分母都必须 >0 才相除，否则返回 None（杜绝负数）。"""
        if numerator is None or denominator is None:
            return None
        if numerator <= 0 or denominator <= 0:
            return None
        r = numerator / denominator
        return r if r >= 0 else None

    return {
        "market_cap": market_cap,
        "PE": ratio(market_cap, net_profit),
        "PB": ratio(market_cap, equity),
        "PS": ratio(market_cap, revenue),
    }


# ------------------------- 展示格式化 -------------------------
def humanize_currency(value):
    if value is None:
        return "-"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f} 亿港元"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f} 万港元"
    return f"{value:.2f} 港元"


def humanize_shares(value):
    if value is None:
        return "-"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f} 亿股"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f} 万股"
    return f"{value:.0f} 股"


def fmt_ratio(value):
    return "-" if value is None else f"{value:.2f} 倍"


def fmt_export(value, decimals=2):
    """导出统一转字符串：数字 -> 文本，None/NaN/空 -> '--'。"""
    if value is None or (isinstance(value, float) and value != value):
        return "--"
    if isinstance(value, str):
        s = value.strip()
        return s if s else "--"
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}"
    return str(value)


# ------------------------- 结果表格 -------------------------
def build_financial_df(conv, raw=None):
    """① 关键财务数据提取表。conv: {字段名: convert_to_base 返回的 dict}；raw: 模型原始 JSON（用于展示面值等参考字段）。"""
    def row(name, kind):
        c = conv.get(name, {})
        raw_value = c.get("raw_value")
        raw_unit = c.get("raw_unit")
        value = c.get("value")
        if c.get("unit_unknown"):
            display = "⚠ 单位未识别（unit_unknown）"
        elif value is None:
            display = "-"
        else:
            display = humanize_currency(value) if kind == "currency" else humanize_shares(value)
        # 全部转成字符串再进表格，避免 float/None 混入导出报错
        return [name,
                fmt_export(raw_value, 2),
                fmt_export(raw_unit),
                fmt_export(value, 0),
                fmt_export(display)]

    rows = [
        row("营业收入", "currency"),
        row("归母净利润", "currency"),
        row("净资产", "currency"),
        row("总股本", "shares"),
    ]
    # 股本面值（人民币面值口径）：仅参考展示，不换算、不参与估值
    face_value, face_unit = extract_field(raw or {}, "股本面值")
    if face_value is not None or face_unit is not None:
        rows.append(["股本面值(人民币·仅参考)",
                     fmt_export(face_value, 2),
                     fmt_export(face_unit),
                     "--",
                     "仅参考，不参与估值"])
    return pd.DataFrame(rows, columns=["项目", "原数值", "原单位", "换算后(港元/股)", "可读显示"])


def build_valuation_df(result):
    """② 估值结果表。"""
    rows = [
        ("总市值", "股价 × 总股本", fmt_export(result["market_cap"]), "股价>0 且总股本>0"),
        ("PE(市盈率)", "总市值 ÷ 归母净利润", fmt_export(result["PE"]), "归母净利润>0 才计算"),
        ("PB(市净率)", "总市值 ÷ 净资产", fmt_export(result["PB"]), "净资产>0 才计算"),
        ("PS(市销率)", "总市值 ÷ 营业收入", fmt_export(result["PS"]), "营业收入>0 才计算"),
    ]
    return pd.DataFrame(rows, columns=["指标", "计算公式", "数值", "计算条件"])


def build_plot(pe, pb, ps):
    """③ 估值倍数柱状图。"""
    items = [("PE", pe), ("PB", pb), ("PS", ps)]
    labels = [n for n, v in items if v is not None]
    values = [round(v, 2) for n, v in items if v is not None]
    fig = go.Figure()
    if values:
        fig.add_trace(go.Bar(x=labels, y=values,
                             text=[f"{v:.2f}" for v in values], textposition="outside"))
        fig.update_layout(title="估值倍数（PE / PB / PS）", yaxis_title="倍数（倍）",
                          height=360, template="plotly_white")
    else:
        fig.add_annotation(text="无可计算的估值倍数（净利润/净资产/营收均非正）",
                           showarrow=False, font=dict(size=14))
        fig.update_layout(height=300, template="plotly_white")
    return fig

# ------------------------- 导出 -------------------------
def _safe_name(name):
    n = (name or "").strip() or "港股财报"
    return re.sub(r'[\\/:*?"<>|]', "_", n)


def df_to_markdown(df):
    """DataFrame -> Markdown 表格（不依赖 tabulate）。"""
    headers = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in df.values.tolist():
        # 兜底：逐个单元格统一转字符串，杜绝 float/None 混入 join
        lines.append("| " + " | ".join(fmt_export(c) for c in r) + " |")
    return "\n".join(lines)


def _fin_df_with_manual(fin_df, manual_total_shares):
    """给财务数据表追加一行「手动填入总股本（亿股）」，仅用于导出，不改动展示表。"""
    fin_export = fin_df.copy()
    manual_val = to_float(manual_total_shares)
    fin_export.loc[len(fin_export)] = ["手动填入总股本（亿股）",
                                       fmt_export(manual_val, 2),
                                       "亿股", "--", "兜底输入，仅用于后台估值"]
    return fin_export


def export_excel(name, fin_df, val_df, manual_total_shares=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{_safe_name(name)}_估值_{ts}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _fin_df_with_manual(fin_df, manual_total_shares).to_excel(writer, sheet_name="财务数据", index=False)
        val_df.to_excel(writer, sheet_name="估值结果", index=False)
    return path


def export_markdown(name, raw, price, fin_df, val_df, manual_total_shares=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{_safe_name(name)}_估值备忘_{ts}.md")
    lines = [
        f"# {name or '港股财报'} 估值备忘",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 报告期：{raw.get('报告期', '-')}",
        f"- 币种：{raw.get('币种', '-')}",
        f"- 最新股价：{price if price is not None else '-'}",
        "",
        "## 关键财务数据",
        df_to_markdown(_fin_df_with_manual(fin_df, manual_total_shares)),
        "",
        "## 估值结果",
        df_to_markdown(val_df),
        "",
        "## 重要提示（假设与局限）",
        "- 总市值 = 最新股价 × 财报披露总股本；未考虑期间股本变动、增发/回购。",
        "- 本工具只做数量级统一（百万/千/亿 → 港元），不做汇率换算；若财报币种非港元，请先人工统一。",
        "- 单位识别不清的字段已标记 unit_unknown 并跳过计算，请人工核对原单位后重试。",
        "- 净利润/净资产/营收为负时，对应 PE/PB/PS 不计算（不输出负数估值）。",
        "- 数据由 AI 从 PDF 提取，可能因表格错乱/识别偏差存在误差，务必对照原始财报逐项核验。",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ------------------------- 主流程回调 -------------------------
def run_analysis(pdf_file, name, price, manual_total_shares=None):
    """按钮回调：PDF 读取 -> DeepSeek 提取 -> 单位换算 -> 估值 -> 导出。"""
    # 1) 读 PDF
    try:
        pdf_path = pdf_file if isinstance(pdf_file, str) else getattr(pdf_file, "name", None)
        text = extract_pdf_text(pdf_path)
    except Exception as e:
        raise gr.Error(f"❌ PDF 读取失败：{e}")
    # 2) 调 DeepSeek
    try:
        content = call_deepseek(text)
    except Exception as e:
        raise gr.Error(f"❌ DeepSeek 调用失败：{e}")
    # 3) 解析 JSON
    try:
        raw = parse_model_output(content)
    except Exception as e:
        raise gr.Error(f"❌ 解析失败：{e}")
    # 4) 提取 + 单位换算（统一到港元；识别不出单位时标记 unit_unknown，不强行计算）
    conv = {}
    for label, kind in [("营业收入", "currency"), ("归母净利润", "currency"),
                        ("净资产", "currency"), ("总股本", "shares")]:
        value, unit = extract_field(raw, label)
        conv[label] = convert_to_base(value, unit, kind)
    revenue = conv["营业收入"]["value"]
    net_profit = conv["归母净利润"]["value"]
    equity = conv["净资产"]["value"]
    # 总股本选择：AI 提取优先；AI 无效时回退手动填入（亿股 -> 股）；两者都无效则不计算市值
    ai_shares = conv["总股本"]["value"]
    manual_shares = None
    m = to_float(manual_total_shares)
    if m is not None and m > 0:
        manual_shares = m * 1e8  # 亿股 -> 股
    if ai_shares is not None and ai_shares > 0:
        shares = ai_shares
        print(f"[日志] 采用 AI 提取总股本：{shares:,.0f} 股")
    elif manual_shares is not None:
        shares = manual_shares
        print(f"[日志] AI 总股本无效，回退使用手动填入总股本：{shares:,.0f} 股")
    else:
        shares = None
        print("[警告] AI 与手动总股本均无效，总市值/PE/PB/PS 不计算")
    unknown_fields = [name for name, c in conv.items() if c.get("unit_unknown")]
    if unknown_fields:
        print(f"[警告] 存在 unit_unknown 字段：{unknown_fields}，对应估值将不计算")
    # 5) 估值
    result = compute_valuations(revenue, net_profit, equity, shares, to_float(price))
    # 6) 建表 / 绘图 / 导出
    fin_df = build_financial_df(conv, raw)
    val_df = build_valuation_df(result)
    fig = build_plot(result["PE"], result["PB"], result["PS"])
    try:
        excel_path = export_excel(name, fin_df, val_df, manual_total_shares)
        md_path = export_markdown(name, raw, to_float(price), fin_df, val_df, manual_total_shares)
    except Exception as e:
        raise gr.Error(f"❌ 导出文件失败：{e}")
    return fin_df, val_df, fig, excel_path, md_path


# ------------------------- UI -------------------------
def build_ui():
    with gr.Blocks(title="港股财报 PE/PB/PS 解析估值") as demo:
        gr.Markdown(
            "# 📊 港股财报 PE / PB / PS 解析估值工具\n"
            "上传**文字版 PDF 财报** → AI 提取关键财务数据 → 自动识别单位并统一换算为「港元」 → "
            "严格「先判断再除法」计算估值倍数（净利润/净资产/营收为负时不计算，不输出负数估值）。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                pdf_file = gr.File(label="① 上传财报 PDF（文字版）", file_types=[".pdf"])
                name = gr.Textbox(label="② 股票名称 / 代码（可选，用于导出文件名）",
                                  placeholder="例如：腾讯控股 00700.HK")
                price = gr.Number(label="③ 最新股价（港元/股）", precision=3)
                manual_total_shares = gr.Number(label="总股本（亿股，可选）",
                                                placeholder="AI自动提取优先，提取失败可手动填入",
                                                value=None)
                btn = gr.Button("开始解析并估值", variant="primary")
            with gr.Column(scale=2):
                fin_table = gr.Dataframe(label="关键财务数据（已统一换算为港元）", wrap=True)
                val_table = gr.Dataframe(label="估值结果", wrap=True)
                plot = gr.Plot(label="估值倍数图")
                with gr.Row():
                    excel_out = gr.File(label="下载 Excel")
                    md_out = gr.File(label="下载 Markdown 备忘")

        btn.click(fn=run_analysis, inputs=[pdf_file, name, price, manual_total_shares],
                  outputs=[fin_table, val_table, plot, excel_out, md_out])
    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860)

