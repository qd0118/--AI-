"""Power BI import-ready fact tables and a sample monthly report."""
from __future__ import annotations

from pathlib import Path
import json

from .analysis import expense_view, pnl, product_view, revenue_bridge
from .agent import draft_report

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exports"


def export() -> None:
    OUT.mkdir(exist_ok=True)
    pnl().to_csv(OUT / "monthly_pnl.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    import pandas as pd
    products = pd.concat([product_view(i).assign(month=i) for i in range(1, 13)], ignore_index=True)
    products.to_csv(OUT / "product_channel.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    expenses = pd.concat([expense_view(i).assign(month=i) for i in range(1, 13)], ignore_index=True)
    expenses.to_csv(OUT / "department_expenses.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    bridges = []
    for month in range(1,13):
        b = revenue_bridge(month)
        for metric, items in [("收入", b["收入"]), ("成本", b["成本"])]:
            for driver, value in items.items():
                bridges.append({"month":month, "metric":metric,"driver":driver,"amount_rmb":round(value,2)})
    pd.DataFrame(bridges).to_csv(OUT / "variance_bridge.csv", index=False, encoding="utf-8-sig")
    report = draft_report(9)
    (OUT / "sample_report_2025_09.txt").write_text(report["report"], encoding="utf-8")
    (OUT / "sample_evidence_2025_09.json").write_text(json.dumps(report["evidence"],ensure_ascii=False,indent=2),encoding="utf-8")


if __name__ == "__main__":
    export()
