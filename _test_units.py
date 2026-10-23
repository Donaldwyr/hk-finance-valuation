import app

print("=" * 60)
print("1) 单位换算自测（统一到港元/股）")
print("=" * 60)
cases = [
    (123.45, "百万", "currency"),
    (12.34, "HK$ million", "currency"),
    (5.6, "千元", "currency"),
    (7.8, "HK$ thousand", "currency"),
    (9.0, "亿元", "currency"),
    (1.5, "港元", "currency"),
    (50.0, "亿股", "shares"),
    (999, "看不懂的单位", "currency"),
]
for v, u, k in cases:
    r = app.convert_to_base(v, u, k)
    print("  unit=%r -> value=%s, unit_unknown=%s" % (u, r["value"], r["unit_unknown"]))

print()
print("=" * 60)
print("2) 估值规则自测（负数 -> None）")
print("=" * 60)
r = app.compute_valuations(revenue=10_000_000_000, net_profit=-500_000_000,
                           equity=2_000_000_000, shares=1_000_000_000, price=10)
print("  净利润为负:", r)
r2 = app.compute_valuations(revenue=10_000_000_000, net_profit=500_000_000,
                            equity=2_000_000_000, shares=1_000_000_000, price=10)
print("  全部为正  :", r2)
print()
print("自测完成")
