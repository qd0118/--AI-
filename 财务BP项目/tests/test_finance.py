"""Independent accounting controls for the case study."""
import unittest

from app.build_data import DISCLOSED, generate
from app.analysis import Scenario, pnl, query, revenue_bridge, scenario
from app.agent import draft_report


class FinanceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generate()

    def test_annual_source_reconciliation(self):
        for product, (revenue, cost) in DISCLOSED.items():
            x = query("SELECT SUM(revenue) r, SUM(cogs) c FROM historical_2024 WHERE product=?", (product,)).iloc[0]
            self.assertAlmostEqual(x.r, revenue, delta=.03)
            self.assertAlmostEqual(x.c, cost, delta=.03)

    def test_monthly_pnl_rollup(self):
        for row in pnl().itertuples(index=False):
            self.assertAlmostEqual(row.actual_gross_profit,row.actual_revenue-row.actual_cogs,delta=.01)
            self.assertAlmostEqual(row.actual_contribution_after_expenses,row.actual_gross_profit-row.actual_opex,delta=.01)
            x = query("SELECT SUM(revenue) rev FROM actual_2025 WHERE month=?",(row.month,)).iloc[0]
            self.assertAlmostEqual(row.actual_revenue,x.rev,delta=.01)

    def test_bridges_reconcile_every_month(self):
        for m in range(1,13):
            b = revenue_bridge(m)
            self.assertAlmostEqual(sum(b["收入"][k] for k in ["销量影响","结构影响","价格影响"]),
                                   b["收入"]["实际收入"]-b["收入"]["预算收入"],delta=.01)
            self.assertAlmostEqual(sum(b["成本"][k] for k in ["销量影响","结构影响","单位成本影响"]),
                                   b["成本"]["实际成本"]-b["成本"]["预算成本"],delta=.01)

    def test_zero_scenario_and_cash_deferral(self):
        baseline = scenario(Scenario(9))
        self.assertAlmostEqual(baseline["incremental_operating_proxy"],0,delta=.01)
        self.assertAlmostEqual(baseline["incremental_cash_proxy"],0,delta=.01)
        delayed = scenario(Scenario(9,collection_delay_pct=.1))
        self.assertAlmostEqual(delayed["incremental_operating_proxy"],0,delta=.01)
        self.assertLess(delayed["incremental_cash_proxy"],0)
        self.assertGreater(delayed["scenario_closing_ar_proxy"],baseline["scenario_closing_ar_proxy"])

    def test_anomaly_and_grounded_fallback(self):
        result = draft_report(9)
        self.assertIn("模拟",result["report"])
        self.assertIn("市场推广",result["report"])
        alerts = result["evidence"]["expense_alerts"]
        self.assertTrue(any(x["account"] == "市场推广" and abs(x["variance_pct"]-.18)<.001 for x in alerts))


if __name__ == "__main__":
    unittest.main()
