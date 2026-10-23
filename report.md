# Project Report: HK Pre-IPO Valuation Tool

## 1. Introduction

Hong Kong is one of the core listing hubs for Greater China enterprises. Before an IPO, investment banking teams and research analysts perform valuation work to estimate the implied equity value and IPO price range for the issuer. The valuation result supports deal discussion, roadshow preparation and IPO pricing.

Manual valuation in Excel is widely used but repetitive and error-prone. This Python tool is built for HK pre-IPO valuation workflow. It automates DCF and comparable company analysis (Comps), computes key multiples, generates valuation summary tables and visual charts, and exports a structured valuation report.

This tool targets the early-stage valuation work done by IBD analysts or equity research associates for Hong Kong IPO candidates. It complements my other SME credit screening project: one covers SME working capital financing at an earlier business stage, while this one focuses on valuation for companies approaching IPO.

## 2. Methodology & Valuation Framework

The tool implements two mainstream valuation approaches used in HK equity capital market (ECM) and IBD: Discounted Cash Flow (DCF) and comparable company analysis.

### 2.1 Discounted Cash Flow (DCF)

Formula logic: Free Cash Flow to Firm (FCFF) discounted by weighted average cost of capital (WACC) plus terminal value.

- FCFF = EBIT × (1 − tax rate) + depreciation & amortisation − capex − change in net working capital
- Terminal value adopts perpetual growth model
- Sensitivity matrix for WACC and perpetual growth rate can be generated to test valuation fluctuation

DCF focuses on intrinsic value driven by long-term cash generation capacity of the business. It is heavily used for manufacturing, consumer and tech issuers listing in Hong Kong.

### 2.2 Comparable Company Analysis (Comps)

The tool takes a peer group of listed HK / A-share comparable firms and calculates trading multiples:

- EV / EBITDA
- P / E
- EV / Revenue
Median and mean multiples are applied to the subject company’s latest financials to derive a relative valuation range.

Relative valuation reflects market pricing sentiment. In HK IPOs, Comps usually carries heavier weight in the final pricing range than standalone DCF.

### 2.3 Valuation Output

The tool merges DCF and Comps results to produce a reference IPO equity value range. It does not give a single fixed price, matching real IBD practice where valuation is presented as a range.

## 3. Data Structure & Modeling Assumptions

### 3.1 Input Data

Input sheet includes historical income statement, balance sheet items, forecast financials, peer list with market data and core parameters (tax rate, WACC inputs, long-term growth). Financial figures are in HKD or converted into HKD for consistency.

### 3.2 Key Assumptions

1. Peer companies are assumed to have comparable business models, end markets and risk profiles; no adjustment for special M&A events or one-off gains by default.
2. Forecast period usually covers 3–5 years before terminal value.
3. Foreign exchange conversion is simplified; complex cross-border tax structure and transfer pricing are not modelled.
4. No separate adjustment for IPO issuance dilution, greenshoe, listing costs or underwriting fees. These are added manually in later formal deal work.
5. Terminal growth rate is constrained below long-term nominal GDP growth to avoid unrealistic valuation.

## 4. Testing Result & Practical Business Interpretation

The tool outputs a valuation range rather than one number. In real HK IBD ECM work:

- DCF often provides a floor or reference value, but is sensitive to WACC and terminal growth assumptions. Small changes in these two inputs can shift valuation materially.
- Comps anchors the valuation to what public investors are currently paying for similar businesses. If peer valuations contract in the secondary market, the IPO pricing range needs to be revised down.

Analysts will flag high-sensitivity parameters to bankers, who then discuss with management to adjust forecast narratives for roadshow.

## 5. System Limitations & Risk Boundaries

This is a valuation auxiliary tool and cannot replace professional IBD valuation judgment.

1. DCF is highly assumption-driven. Minor changes in long-term growth or WACC can create large swings in enterprise value.
2. Comps quality depends entirely on peer selection. Poor peer screening leads to misleading relative valuation.
3. It does not incorporate deal-specific factors: IPO demand, investor sentiment, sector rotation, lock-up arrangements, sponsor reputation. These are critical for HK IPO pricing.
4. No advanced adjustments: control premium / discount, illiquidity discount, contingent consideration, complex convertible instruments.
5. Forecasts are taken as given input; the tool does not audit or challenge the reasonableness of management forecasts.

## 6. Future Optimization & Iteration Direction

1. Add precedent transaction analysis (Precedent Deals), the third core valuation method widely used in IBD.
2. Automatically pull peer market data via financial APIs, instead of manual copy-paste.
3. Build automatic dilution calculation for new shares issued in the IPO and greenshoe option.
4. Add sector-specific calibration: different ranges of WACC and terminal growth for healthcare, consumer, real estate and technology names.
5. Generate formatted valuation slide tables ready for banker presentation decks.

## 7. Conclusion

This lightweight pre-IPO valuation tool simulates the core valuation workflow for Hong Kong ECM / IBD analysts. It standardises FCFF calculation, DCF discounting and comparable multiples computation, reduces repetitive Excel work and lowers manual arithmetic error.

The project clearly separates mechanical calculation from qualitative deal judgement. It demonstrates my understanding of two core valuation methodologies used for HK IPOs. Together with the SME credit screening repo, it shows my end-to-end exposure to corporate financing: from early-stage SME credit review all the way to pre-IPO valuation.
