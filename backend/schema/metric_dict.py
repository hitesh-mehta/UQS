"""
Domain metric dictionary — ensures consistent terminology across queries.
Prevents confusion when multiple teams/roles use different names for the same metric.

Example: "Revenue", "Sales", "Income", "Earnings" → all map to SUM(revenue) on sales_fact_view

Admins can extend this via the admin API. The dictionary is injected into LLM prompts
so the model always uses the canonical SQL expression.
"""
from __future__ import annotations

from pydantic import BaseModel


class MetricDefinition(BaseModel):
    canonical_name: str            # e.g. "Total Revenue"
    aliases: list[str]             # e.g. ["revenue", "sales", "income", "earnings"]
    sql_expression: str            # e.g. "SUM(sf.revenue)"
    requires_tables: list[str]     # e.g. ["sales_fact_view sf"]
    description: str
    unit: str                      # e.g. "$", "%", "count"


# ── Default metric dictionary (extend per customer) ───────────────────────────
DEFAULT_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        canonical_name="Total Revenue",
        aliases=["revenue", "sales", "income", "earnings", "total sales"],
        sql_expression="SUM(sf.revenue)",
        requires_tables=["sales_fact_view sf"],
        description="Sum of all revenue values in the given period",
        unit="$",
    ),
    MetricDefinition(
        canonical_name="Average Order Value",
        aliases=["aov", "average order", "avg order value", "average purchase"],
        sql_expression="AVG(sf.revenue)",
        requires_tables=["sales_fact_view sf"],
        description="Average revenue per transaction",
        unit="$",
    ),
    MetricDefinition(
        canonical_name="Transaction Count",
        aliases=["transactions", "orders", "number of orders", "trades", "count"],
        sql_expression="COUNT(sf.id)",
        requires_tables=["sales_fact_view sf"],
        description="Total number of transactions",
        unit="count",
    ),
    MetricDefinition(
        canonical_name="Unique Customers",
        aliases=["customers", "unique buyers", "distinct customers", "customer count"],
        sql_expression="COUNT(DISTINCT sf.customer_id)",
        requires_tables=["sales_fact_view sf"],
        description="Number of distinct customers who made a purchase",
        unit="count",
    ),
    MetricDefinition(
        canonical_name="Churn Rate",
        aliases=["churn", "churn rate", "attrition", "customer loss"],
        sql_expression="AVG(cd.churn_risk)",
        requires_tables=["rm_customer_view cd"],
        description="Average churn risk score across customers (0=no risk, 1=certain churn)",
        unit="%",
    ),
]


class MetricDictionary:
    def __init__(self, metrics: list[MetricDefinition] | None = None):
        self._metrics = {m.canonical_name: m for m in (metrics or DEFAULT_METRICS)}

    def add(self, metric: MetricDefinition) -> None:
        self._metrics[metric.canonical_name] = metric

    def find_by_alias(self, term: str) -> MetricDefinition | None:
        """Find a metric by any of its aliases (case-insensitive)."""
        term_lower = term.lower()
        for metric in self._metrics.values():
            if term_lower in [a.lower() for a in metric.aliases]:
                return metric
            if term_lower in metric.canonical_name.lower():
                return metric
        return None

    def format_for_llm(self) -> str:
        """Format the metric dictionary for injection into LLM prompts."""
        lines = ["Canonical Metric Definitions (use these SQL expressions):"]
        for metric in self._metrics.values():
            lines.append(f"\n{metric.canonical_name} ({metric.unit}):")
            lines.append(f"  Aliases: {', '.join(metric.aliases)}")
            lines.append(f"  SQL: {metric.sql_expression}")
            lines.append(f"  From: {', '.join(metric.requires_tables)}")
        return "\n".join(lines)

    def all_metrics(self) -> list[MetricDefinition]:
        return list(self._metrics.values())


# ── Global singleton ──────────────────────────────────────────────────────────
metric_dict = MetricDictionary()
