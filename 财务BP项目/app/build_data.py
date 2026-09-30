"""Generate reproducible, clearly synthetic operating data and a SQLite mart."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE = "https://disc.static.szse.cn/disc/disk03/finalpage/2025-04-28/9bd3ae70-7998-4fbe-99ff-87b7ebd43cb8.PDF"

# RMB, from the company's 2024 annual report, pp. 22–23 / consolidated P&L.
DISCLOSED = {
    "充电储能": (12667006821.10, 7415203131.88),
    "智能创新": (6336476919.10, 3391303871.48),
    "智能影音": (5692427101.62, 3108036030.98),
}
REPORTED = {
    "company_revenue": 24710080329.34,
    "company_cogs": 13918403694.15,
    "selling_expense": 5569790884.12,
    "admin_expense": 868731901.96,
}
REGIONS = ["北美", "欧洲", "日本", "中国", "其他"]
REGION_WEIGHTS = [0.49, 0.28, 0.12, 0.04, 0.07]  # synthetic; not reported segment data
CHANNELS = ["线上", "线下"]
CHANNEL_WEIGHTS = [0.713, 0.287]
PRODUCT_WEIGHTS = {"充电储能": 0.511, "智能创新": 0.257, "智能影音": 0.232}
UNIT_BASE = {"充电储能": 170, "智能创新": 450, "智能影音": 350}


def allocate(total: float, weights: np.ndarray) -> np.ndarray:
    vals = np.round(total * weights / weights.sum(), 2)
    vals[-1] = round(total - vals[:-1].sum(), 2)
    return vals


def generate(seed: int = 20260929) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    months = np.array([0.78, 0.74, 0.82, 0.91, 0.95, 0.97, 0.99, 1.04, 1.11, 1.15, 1.45, 1.09])
    cells = [(p, c, r, m) for p in DISCLOSED for c in CHANNELS for r in REGIONS for m in range(1, 13)]
    records = []
    for product in DISCLOSED:
        subset = [(p, c, r, m) for (p, c, r, m) in cells if p == product]
        w = np.array([CHANNEL_WEIGHTS[CHANNELS.index(c)] * REGION_WEIGHTS[REGIONS.index(r)]
                      * months[m - 1] * rng.uniform(0.94, 1.06) for _, c, r, m in subset])
        annual_rev, annual_cost = DISCLOSED[product]
        revenues = allocate(annual_rev, w)
        costs = allocate(annual_cost, w * np.array([1.07 if c == "线下" else 0.972 for _, c, _, _ in subset]))
        for (p, c, r, m), revenue, cost in zip(subset, revenues, costs):
            qty = max(1, round(revenue / (UNIT_BASE[p] * (1.03 if c == "线下" else 1))))
            records.append(dict(year=2024, month=m, product=p, channel=c, region=r,
                                units=qty, revenue=float(revenue), cogs=float(cost),
                                price=float(revenue / qty), unit_cost=float(cost / qty),
                                data_status="模拟明细；产品年度收入和成本与公开年报校准"))
    history = pd.DataFrame(records)
    assert all(abs(history.loc[history["product"] == p, k].sum() - v[i]) < .05
               for p, v in DISCLOSED.items() for i, k in enumerate(["revenue", "cogs"]))

    budget, actual = [], []
    growth = {"充电储能": 1.13, "智能创新": 1.20, "智能影音": 1.08}
    for x in history.itertuples(index=False):
        key = (x.product, x.channel, x.region, x.month)
        bq = round(x.units * growth[x.product] * (1.03 if x.channel == "线上" else 0.99))
        bp = x.price * 1.025
        bc = x.unit_cost * 1.035
        budget.append(dict(year=2025, month=x.month, product=x.product, channel=x.channel, region=x.region,
                           units=bq, price=bp, unit_cost=bc, revenue=bq * bp, cogs=bq * bc,
                           data_status="2025模拟预算"))
        shock = 0.88 if (x.month in [8, 9] and x.channel == "线下" and x.product == "智能影音") else 1
        aq = round(bq * shock * rng.uniform(.94, 1.07))
        ap = bp * (0.955 if x.channel == "线上" and x.month >= 8 else 1) * rng.uniform(.985, 1.012)
        ac = bc * (1.07 if x.region == "欧洲" and x.month >= 7 else 1) * rng.uniform(.99, 1.025)
        actual.append(dict(year=2025, month=x.month, product=x.product, channel=x.channel, region=x.region,
                           units=aq, price=ap, unit_cost=ac, revenue=aq * ap, cogs=aq * ac,
                           data_status="2025模拟实际"))
    budget = pd.DataFrame(budget)
    actual = pd.DataFrame(actual)
    # Simulate monthly department expense ledgers. The report only anchors 2024 annual consolidated totals.
    accounts = [
        ("市场", "市场推广", .40), ("销售", "平台服务", .35),
        ("销售", "人员费用", .17), ("运营", "仓储履约", .08),
        ("管理", "管理费用", None),
    ]
    expenses = []
    base_selling = REPORTED["selling_expense"]
    for month in range(1, 13):
        rev_factor = float(budget.loc[budget.month == month, "revenue"].sum() /
                           history.loc[history.month == month, "revenue"].sum())
        month_weight = months[month - 1] / months.sum()
        for dept, account, weight in accounts:
            old_annual = REPORTED["admin_expense"] if weight is None else base_selling * weight
            b = old_annual * month_weight * (rev_factor if weight is not None else 1.07)
            a = b * rng.uniform(.97, 1.04)
            reason = "一般波动"
            if account == "市场推广" and month == 9:
                a = b * 1.18
                reason = "模拟案例：季度推广提前投放，费用按当月发生计入"
            expenses.append(dict(year=2025, month=month, department=dept, account=account,
                                 budget=b, actual=a, reason=reason, data_status="模拟预算与模拟费用实际"))
    expenses = pd.DataFrame(expenses)

    # Monthly credit sales and cash collections by channel; the opening balance is explicitly synthetic.
    ar_rows = []
    opening = 400_000_000.0
    for month in range(1, 13):
        a = actual.loc[actual.month == month].groupby("channel").revenue.sum()
        current_online, current_offline = float(a.get("线上", 0)), float(a.get("线下", 0))
        prev = actual.loc[actual.month == month - 1].groupby("channel").revenue.sum() if month > 1 else pd.Series(dtype=float)
        prev2 = actual.loc[actual.month == month - 2].groupby("channel").revenue.sum() if month > 2 else pd.Series(dtype=float)
        collection = .90 * current_online + .15 * current_offline
        if month > 1:
            collection += .10 * float(prev.get("线上", 0)) + .70 * float(prev.get("线下", 0))
        if month > 2:
            collection += .15 * float(prev2.get("线下", 0))
        elif month == 1:
            collection += .55 * opening
        elif month == 2:
            collection += .45 * opening
        closing = opening + current_online + current_offline - collection
        ar_rows.append(dict(year=2025, month=month, opening_ar=opening,
                            invoiced=current_online + current_offline, collections=collection,
                            closing_ar=closing, data_status="模拟应收和收款；非公司披露数据"))
        opening = closing
    ar = pd.DataFrame(ar_rows)

    DATA.mkdir(parents=True, exist_ok=True)
    tables = {"historical_2024": history, "budget_2025": budget, "actual_2025": actual,
              "expense_2025": expenses, "receivables_2025": ar}
    with sqlite3.connect(DATA / "finance_bp.sqlite") as conn:
        for name, frame in tables.items():
            frame.to_sql(name, conn, if_exists="replace", index=False)
            frame.to_csv(DATA / f"{name}.csv", index=False, encoding="utf-8-sig", float_format="%.6f")
        conn.executescript("""
        DROP VIEW IF EXISTS vw_monthly_pnl;
        CREATE VIEW vw_monthly_pnl AS
        WITH b AS (SELECT month, SUM(revenue) AS budget_revenue, SUM(cogs) AS budget_cogs FROM budget_2025 GROUP BY month),
             a AS (SELECT month, SUM(revenue) AS actual_revenue, SUM(cogs) AS actual_cogs FROM actual_2025 GROUP BY month),
             e AS (SELECT month, SUM(budget) AS budget_opex, SUM(actual) AS actual_opex FROM expense_2025 GROUP BY month)
        SELECT a.month, b.budget_revenue, a.actual_revenue, b.budget_cogs, a.actual_cogs,
               b.budget_revenue-b.budget_cogs AS budget_gross_profit,
               a.actual_revenue-a.actual_cogs AS actual_gross_profit,
               e.budget_opex, e.actual_opex,
               b.budget_revenue-b.budget_cogs-e.budget_opex AS budget_contribution_after_expenses,
               a.actual_revenue-a.actual_cogs-e.actual_opex AS actual_contribution_after_expenses,
               r.collections, r.closing_ar
        FROM a JOIN b USING(month) JOIN e USING(month) JOIN receivables_2025 r USING(month);
        """)
    (DATA / "source_manifest.json").write_text(json.dumps({
        "company": "安克创新科技股份有限公司", "period": "2024", "source": SOURCE,
        "reported_controls_rmb": REPORTED, "reported_product_revenue_cost_rmb": DISCLOSED,
        "limitations": "Only product-level annual revenue/cost and consolidated controls are public. All row-level, 2025, budgets, receivables and scenarios are synthetic; 2024 product totals are calibrated exactly. The three product families exclude small other income. No inference about the company's actual 2025 performance is intended.",
        "random_seed": seed,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return tables


if __name__ == "__main__":
    frames = generate()
    print({k: len(v) for k, v in frames.items()})
