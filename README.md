# hk-finance-valuation

> A local Gradio tool that parses Hong Kong–listed company annual-report PDFs, extracts key financials with an LLM, auto-normalizes report units to **HKD**, and computes **PE / PB / PS** multiples. Built for IBD valuation practice and as a personal portfolio project.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Gradio](https://img.shields.io/badge/UI-Gradio-orange)

---

## 1. Project Intro

**Motivation.** Hong Kong equity research and IBD valuation work both start from the same place: tearing a listed company's annual report down to a handful of normalized numbers (revenue, attributable net profit, net assets, share count) and turning them into trading multiples. This project automates that repetitive "read → extract → normalize units → compute multiples" workflow so I can:

- Practice sell-side / IBD-style financial statement dissection.
- Drill the unit conventions of HK financial reports (`HK$ million`, `千元`, `亿元`, `亿股`, …) that trip people up in real deals.
- Build a clean, demonstrable end-to-end artifact (PDF → LLM extraction → valuation → Excel/Markdown report) for interviews.

**What it is not.** This is a learning/study tool, not production software. The "AI" extraction step uses the DeepSeek chat API and can hallucinate — every number must be re-checked against the source PDF (see [Notes & Limitations](#5-notes--limitations)).

---

## 2. Features

- **PDF text extraction** via `pdfplumber` (text-based PDFs only; scanned/image PDFs are rejected with a friendly message).
- **LLM financial extraction** via DeepSeek (`deepseek-chat`) — pulls:
  - 营业收入 (revenue), 归母净利润 (net profit attributable to parent), 净资产 (net assets/equity), 总股本 (total shares), plus 报告期 (period) and 币种 (currency, reference only).
- **Strict structured output**: every field is returned as `{"数值": value, "单位": unit}` — never a bare number.
- **Automatic unit normalization to HKD** (and shares to 股):

  | Report unit | Multiply to HKD |
  |---|---|
  | `HK$ million` / `百万` | × 1,000,000 |
  | `千元` / `HK$ thousand` | × 1,000 |
  | `亿元` | × 100,000,000 |
  | `十亿` | × 1,000,000,000 |
  | `万` | × 10,000 |
  | `港元` / `港币` / `HKD` / `HK$` | × 1 |

  Shares: `亿股` × 10⁸, `万股` × 10⁴, `股` × 1.
- **Guard-rails**:
  - Unrecognized units are flagged `unit_unknown` and skipped (never force-calculated).
  - Multiples are computed only when both numerator and denominator are **> 0**; negative/invalid values return `None` (no negative PE/PB/PS).
- **Interactive UI** (Gradio): financial-data table, valuation table, and a Plotly bar chart.
- **Export** to Excel (`.xlsx`) and a Markdown memo (`.md`).
- **Terminal logging** of every conversion (raw value → raw unit → factor → converted value) for debugging.
- **Self-test** script (`_test_units.py`) that validates unit conversion and valuation rules without calling the API.

---

## 3. Environment Setup

**Hardware note.** Primary dev machine is a Windows gaming laptop (Intel i9-13900HX + RTX 5070 Ti + 16 GB RAM); a lightweight MacBook is used only for viewing/debugging. The machine also hosts a broader conda / PyTorch / transformers stack for other ML work — **this project does not use a local GPU or PyTorch**, because extraction runs against DeepSeek's cloud API. Only the lightweight packages in `requirements.txt` are required.

```bash
# 1) Create and activate a conda environment (Python 3.11 recommended)
conda create -n finance-valuation python=3.11 -y
conda activate finance-valuation

# 2) Install dependencies
pip install -r requirements.txt

# 3) Configure the DeepSeek API key
cp .env.example .env          # Windows cmd: copy .env.example .env
#    then edit .env and set:  DEEPSEEK_API_KEY=sk-...

# 4) Launch the app
python app.py
```

The web UI is served at **http://localhost:7860** (bound to `0.0.0.0`).

## 4. Quick Start

1. Get a **DeepSeek API key** and put it in `.env` (see [Environment Setup](#3-environment-setup)).
2. Prepare a **text-based** annual-report PDF (must have a text layer).
3. Launch `python app.py` and open `http://localhost:7860`.
4. Upload the PDF, optionally enter the ticker/name and the **latest price (HKD/share)**, then click **开始解析并估值**.
5. Review the financial-data and valuation tables, then download the Excel and Markdown reports from `outputs/`.

Run the offline self-test (no API call) to sanity-check unit conversion and valuation rules:

```bash
python _test_units.py
```

---

## 5. Notes & Limitations

- **LLM hallucination is real.** The DeepSeek extraction step can mis-read, invent, or omit figures, especially on dense/footnoted tables. **This tool is for learning only — never use its output for real investment decisions.**
- **Manual review is mandatory.** Always cross-check every extracted number and unit against the source PDF before trusting a multiple.
- **Model recognition errors.** Table layout, OCR-less scans, and unusual fonts can shift decimals or units (e.g., `'000` vs `million`). The `unit_unknown` flag exists precisely to stop silent miscalculation.
- **No FX conversion.** The tool normalizes *magnitude* units (million/thousand/亿) to HKD but does **not** convert between currencies. If the report is in RMB/USD, you must convert to HKD yourself first.
- **Static share count.** Market cap = latest price × reported share count; it ignores intra-period share changes, issuance, and buybacks.
- **Point-in-time estimate.** Multiples use a single latest price; no forward estimates, DCF, comps, or model risk adjustment.

---

## 6. Known Issues & Pitfalls

Things we actually hit while building this (so you don't repeat them):

1. **WSL virtualization errors.** Running the UI under WSL2 on Windows sometimes fails with GPU/virtualization errors. Fix: run natively in a plain conda env on Windows, or (if you need WSL) enable virtualization in BIOS and update to the latest WSL2.
2. **Port 7860 already in use.** Gradio's default port collides when another instance is running. Fix: kill the old process, or change `server_port` in `app.py`'s `demo.launch(...)`.
   ```bash
   # Windows (PowerShell)
   netstat -ano | findstr :7860
   taskkill /PID <pid> /F
   ```
3. **Export type error — `sequence item 2: expected str instance, float found`.** Cause: `None` values became `NaN` (float) when building the `pandas.DataFrame`, then leaked into `" | ".join(...)` during Markdown export. Fix: a single `fmt_export()` helper converts every cell to `str` (numbers → formatted text, `None`/`NaN` → `"--"`) before any join/export.
4. **Mixed units in HK reports.** A single report can mix `HK$ million`, `千元`, `亿元`, and `亿股`/`万股`/`股`. The matcher walks a longest-first factor list (`十亿` → `亿` → `百万` → `万` → `千`…) so `百万` isn't misread as `万`, and anything unrecognized is flagged `unit_unknown` instead of being guessed.

---

## 7. Project Structure

```
hk-finance-valuation/
├── app.py              # Main app: Gradio UI + DeepSeek extraction + unit conversion + valuation + export
├── requirements.txt    # Python dependencies
├── .env.example        # Template for DEEPSEEK_API_KEY (never commit the real .env)
├── .gitignore          # Ignores .env, __pycache__, *.pyc, *.log
├── _test_units.py      # Offline self-test for unit conversion & valuation rules
├── outputs/            # Generated Excel / Markdown reports
└── README.md           # This file
```

---

## 8. License

MIT License

Copyright (c) 2026 hk-finance-valuation contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

# hk-finance-valuation（中文）

> 一个本地 Gradio 工具：解析港股上市公司年报 PDF，用大模型抽取关键财务数据，自动识别财报单位并统一换算成**港元**，计算 **PE / PB / PS** 估值倍数。用于港股 IBD 估值练习，也是个人作品集项目。

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Gradio](https://img.shields.io/badge/UI-Gradio-orange)

---

## 1. 项目简介

**开发动机。** 港股研究和 IBD 估值的工作起点是一样的：把一家上市公司的年报拆成几个标准化数字（营收、归母净利润、净资产、总股本），再换算成交易倍数。本项目把「读 → 抽取 → 统一单位 → 算倍数」这套重复流程自动化，目的是：

- 练习卖方 / IBD 风格的财报拆解。
- 吃透港股财报的单位写法（`HK$ million`、`千元`、`亿元`、`亿股`……），这些在真实项目里很容易踩坑。
- 产出一个完整、可展示的端到端作品（PDF → 大模型抽取 → 估值 → Excel/Markdown 报表），用于面试。

**它不是什么。** 这是一个学习/练习工具，不是生产软件。「AI 抽取」环节走的是 DeepSeek 云端 API，存在幻觉，所有数字必须对照原 PDF 人工复核（见[注意事项与局限](#5-注意事项与局限)）。

---

## 2. 功能清单

- **PDF 文字抽取**（`pdfplumber`）：仅支持文字版 PDF，扫描/图片版会被友好提示拒绝。
- **大模型财务抽取**（DeepSeek `deepseek-chat`）：抽取
  - 营业收入、归母净利润、净资产（归母股东权益）、总股本，以及报告期、币种（仅参考）。
- **严格结构化输出**：每个字段都返回 `{"数值": value, "单位": unit}`，绝不只返回裸数字。
- **自动识别单位并统一换算为港元**（股本统一换算为「股」）：

  | 财报单位 | 换算为港元 |
  |---|---|
  | `HK$ million` / `百万` | × 1,000,000 |
  | `千元` / `HK$ thousand` | × 1,000 |
  | `亿元` | × 100,000,000 |
  | `十亿` | × 1,000,000,000 |
  | `万` | × 10,000 |
  | `港元` / `港币` / `HKD` / `HK$` | × 1 |

  股本：`亿股` × 10⁸、`万股` × 10⁴、`股` × 1。
- **兜底保护**：
  - 识别不出单位时标记 `unit_unknown` 并跳过计算（绝不强行算）。
  - 只有当分子、分母都 **> 0** 时才做除法；负数/非法值返回 `None`（不输出负的 PE/PB/PS）。
- **交互式界面**（Gradio）：财务数据表、估值表、Plotly 柱状图。
- **导出** Excel（`.xlsx`）和 Markdown 备忘（`.md`）。
- **终端日志**：逐条打印原始值 → 原始单位 → 换算系数 → 换算后结果，方便调试。
- **自测脚本**（`_test_units.py`）：不调 API，即可验证单位换算与估值规则。

---

## 3. 环境搭建

**硬件说明。** 主力开发机是 Windows 游戏本（i9-13900HX + RTX 5070 Ti + 16 GB 内存）；一台轻薄 MacBook 仅用于查看、调试。这台机器上还装了 conda / PyTorch / transformers 这套更重的环境用于其它 ML 任务——**本项目不依赖本地 GPU 或 PyTorch**，因为抽取走的是 DeepSeek 云端 API，只需要 `requirements.txt` 里的轻量依赖即可。

```bash
# 1) 新建并激活 conda 环境（推荐 Python 3.11）
conda create -n finance-valuation python=3.11 -y
conda activate finance-valuation

# 2) 安装依赖
pip install -r requirements.txt

# 3) 配置 DeepSeek API Key
cp .env.example .env          # Windows cmd 下用：copy .env.example .env
#    然后编辑 .env，写入：  DEEPSEEK_API_KEY=sk-...

# 4) 启动
python app.py
```

网页界面默认运行在 **http://localhost:7860**（监听 `0.0.0.0`）。

## 4. 快速开始

1. 拿到 **DeepSeek API Key**，写入 `.env`（见[环境搭建](#3-环境搭建)）。
2. 准备一份**文字版**年报 PDF（必须有文字层）。
3. 运行 `python app.py`，浏览器打开 `http://localhost:7860`。
4. 上传 PDF，可选填股票名称/代码和**最新股价（港元/股）**，点「开始解析并估值」。
5. 查看财务数据表和估值表，从 `outputs/` 下载 Excel 和 Markdown 报表。

离线自测（不调 API），快速验证单位换算与估值规则：

```bash
python _test_units.py
```

---

## 5. 注意事项与局限

- **大模型存在幻觉。** DeepSeek 抽取环节可能看错、编造或漏掉数字，尤其在密集表格/脚注上。**本工具仅供学习，切勿用于真实投资决策。**
- **必须人工复核。** 使用任何倍数前，务必把每个抽取出的数字和单位与原 PDF 逐项核对。
- **模型识别会有误差。** 表格排版、无 OCR 的扫描件、特殊字体都可能导致小数位或单位错位（例如 `'000` 和 `million` 混淆）。`unit_unknown` 标记正是为了阻断这种「静默算错」。
- **不做汇率换算。** 工具只统一「数量级」单位（百万/千/亿 → 港元），**不**做币种间换算；若财报是人民币/美元，需要你先自行换算成港元。
- **静态股本。** 总市值 = 最新股价 × 披露总股本，未考虑期间股本变动、增发、回购。
- **时点估计。** 倍数只用单一最新股价，不含前瞻预测、DCF、可比公司或模型风险调整。

---

## 6. 已知问题与踩坑记录

下面是我们开发过程中真实踩过的坑（帮你少走弯路）：

1. **WSL 虚拟化报错。** 在 Windows 的 WSL2 里跑 UI 有时会因 GPU/虚拟化报错。解决：直接在 Windows 原生 conda 环境里跑；若必须用 WSL，先在 BIOS 开启虚拟化并升级到最新版 WSL2。
2. **端口 7860 被占用。** Gradio 默认端口被其它实例占用时启动失败。解决：杀掉旧进程，或改 `app.py` 里 `demo.launch(...)` 的 `server_port`。
   ```bash
   # Windows（PowerShell）
   netstat -ano | findstr :7860
   taskkill /PID <pid> /F
   ```
3. **导出类型报错 — `sequence item 2: expected str instance, float found`。** 原因：构建 `pandas.DataFrame` 时 `None` 被转成 `NaN`（float），又在 Markdown 导出的 `" | ".join(...)` 里混入了 float。解决：统一用 `fmt_export()` 把每个单元格转成 `str`（数字→文本、`None`/`NaN`→`"--"`），再做 join/导出。
4. **港股财报多种单位混用。** 同一份财报可能混用 `HK$ million`、`千元`、`亿元` 和 `亿股`/`万股`/`股`。匹配器按「从长到短」遍历系数表（`十亿` → `亿` → `百万` → `万` → `千`…），避免 `百万` 被误当成 `万`；识别不出的单位统一标记 `unit_unknown`，不瞎猜。

---

## 7. 项目结构

```
hk-finance-valuation/
├── app.py              # 主程序：Gradio 界面 + DeepSeek 抽取 + 单位换算 + 估值 + 导出
├── requirements.txt    # Python 依赖
├── .env.example        # DEEPSEEK_API_KEY 模板（真实 .env 不要提交）
├── .gitignore          # 忽略 .env、__pycache__、*.pyc、*.log
├── _test_units.py      # 离线自测：单位换算 + 估值规则
├── outputs/            # 生成的 Excel / Markdown 报表
└── README.md           # 本文件
```

---

## 8. License

本项目采用 **MIT License** 开源。

MIT License

Copyright (c) 2026 hk-finance-valuation contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
