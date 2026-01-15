from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Tuple

import duckdb
import pandas as pd


def _ensure_datetime(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def build_sales_kpis(orders_df: pd.DataFrame) -> Dict[str, object]:
    df = orders_df.copy()
    df = _ensure_datetime(df, "created_at")
    df["total"] = pd.to_numeric(df.get("total", 0), errors="coerce").fillna(0.0)
    df["status"] = df.get("status", "").astype(str).str.lower()
    df["channel"] = df.get("channel", "Direto").astype(str)
    df = df[df["created_at"].notna()]

    last_30 = df[df["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=30))]
    last_30 = last_30[last_30["status"] != "cancelado"]

    if last_30.empty:
        return {"empty": True}

    revenue = last_30["total"].sum()
    orders_count = last_30.shape[0]
    ticket = _safe_div(revenue, orders_count)

    paid = last_30[last_30["status"].isin(["pago", "aprovado", "faturado"])].shape[0]
    approval_rate = _safe_div(paid, orders_count) * 100

    last_60 = df[df["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=60))]
    last_60 = last_60[last_60["status"] != "cancelado"]
    prev_30 = last_60[last_60["created_at"] < (pd.Timestamp.now() - pd.Timedelta(days=30))]
    prev_revenue = prev_30["total"].sum()
    delta = ((_safe_div(revenue - prev_revenue, prev_revenue)) * 100) if prev_revenue else 0.0

    trend = (
        last_30.groupby(last_30["created_at"].dt.date)["total"]
        .sum()
        .reset_index(name="sales")
        .rename(columns={"created_at": "date"})
    )
    trend["ma7"] = trend["sales"].rolling(7, min_periods=1).mean()

    channel_share = (
        last_30.groupby("channel")["total"].sum().reset_index().sort_values("total", ascending=False)
    )

    top_products = (
        last_30.groupby("product_name")["total"].sum().reset_index().sort_values("total", ascending=False)
    )
    top_products = top_products.head(5) if "product_name" in last_30 else pd.DataFrame()

    top_sellers = (
        last_30.groupby("seller")["total"].sum().reset_index().sort_values("total", ascending=False)
    )
    top_sellers = top_sellers.head(5) if "seller" in last_30 else pd.DataFrame()

    return {
        "empty": False,
        "revenue": revenue,
        "delta": delta,
        "ticket": ticket,
        "approval_rate": approval_rate,
        "trend": trend,
        "channel_share": channel_share,
        "top_products": top_products,
        "top_sellers": top_sellers,
    }


def build_inventory_kpis(stock_df: pd.DataFrame, sales_df: pd.DataFrame) -> Dict[str, object]:
    stock = stock_df.copy()
    stock["sku"] = stock.get("sku", "").astype(str)
    stock["saldo"] = pd.to_numeric(stock.get("saldo", 0), errors="coerce").fillna(0.0)
    stock["custo"] = pd.to_numeric(stock.get("custo", 0), errors="coerce").fillna(0.0)
    stock["valor_estoque"] = stock["saldo"] * stock["custo"]

    sales = sales_df.copy()
    sales = _ensure_datetime(sales, "created_at")
    sales = sales[sales["created_at"].notna()]
    sales["qty"] = pd.to_numeric(sales.get("qty", 0), errors="coerce").fillna(0.0)
    sales["sku"] = sales.get("sku", "").astype(str)

    if stock.empty:
        return {"empty": True}

    last_90 = sales[sales["created_at"] >= (pd.Timestamp.now() - pd.Timedelta(days=90))]
    daily_sales = last_90.groupby("sku")["qty"].sum() / 90.0
    daily_sales = daily_sales.reset_index().rename(columns={"qty": "daily_qty"})

    merged = stock.merge(daily_sales, on="sku", how="left")
    merged["daily_qty"] = merged["daily_qty"].fillna(0.0)
    merged["coverage_days"] = merged.apply(
        lambda row: _safe_div(row["saldo"], row["daily_qty"]) if row["daily_qty"] > 0 else 999,
        axis=1,
    )

    rupture = merged[merged["coverage_days"] < 15].copy()
    rupture["status"] = "Crítico"

    dead_stock = merged[(merged["saldo"] > 5) & (merged["daily_qty"] == 0)].copy()
    dead_stock["trava"] = dead_stock["saldo"] * dead_stock["custo"]

    total_stock_value = merged["valor_estoque"].sum()

    revenue_by_sku = sales_df.copy()
    revenue_by_sku["total"] = pd.to_numeric(revenue_by_sku.get("total", 0), errors="coerce").fillna(0.0)
    revenue_by_sku = revenue_by_sku.groupby("sku")["total"].sum().reset_index().sort_values("total", ascending=False)
    revenue_by_sku["cum_share"] = revenue_by_sku["total"].cumsum() / max(revenue_by_sku["total"].sum(), 1)
    revenue_by_sku["class"] = revenue_by_sku["cum_share"].apply(
        lambda x: "A" if x <= 0.8 else ("B" if x <= 0.95 else "C")
    )

    return {
        "empty": False,
        "stock_value": total_stock_value,
        "rupture": rupture,
        "dead_stock": dead_stock,
        "abc": revenue_by_sku,
    }


def build_finance_kpis(ar_df: pd.DataFrame, ap_df: pd.DataFrame) -> Dict[str, object]:
    ar = ar_df.copy()
    ap = ap_df.copy()
    ar["due_date"] = pd.to_datetime(ar.get("due_date", None), errors="coerce")
    ap["due_date"] = pd.to_datetime(ap.get("due_date", None), errors="coerce")
    ar["amount"] = pd.to_numeric(ar.get("amount", 0), errors="coerce").fillna(0.0)
    ap["amount"] = pd.to_numeric(ap.get("amount", 0), errors="coerce").fillna(0.0)

    if ar.empty and ap.empty:
        return {"empty": True}

    today = pd.Timestamp.now()
    overdue = ar[(ar["due_date"] < today) & (ar.get("status", "").astype(str).str.lower() != "pago")]
    inadimplencia = _safe_div(overdue["amount"].sum(), max(ar["amount"].sum(), 1)) * 100

    projected = pd.concat(
        [
            ar[["due_date", "amount"]].assign(type="Receber"),
            ap[["due_date", "amount"]].assign(type="Pagar"),
        ]
    )
    projected = projected[projected["due_date"].notna()]
    projected = projected[projected["due_date"] <= today + pd.Timedelta(days=30)]

    return {
        "empty": False,
        "inadimplencia": inadimplencia,
        "projected": projected,
    }


def generate_mock_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime.now()
    orders = []
    for i in range(60):
        orders.append(
            {
                "created_at": base - timedelta(days=i),
                "total": 1000 + (i * 20),
                "status": "pago" if i % 7 else "cancelado",
                "channel": "Mercado Livre" if i % 2 else "Shopee",
                "product_name": f"Produto {i % 8}",
                "seller": f"Vendedor {i % 3}",
                "sku": f"SKU{i % 10}",
                "qty": 1 + (i % 5),
            }
        )
    stock = []
    for i in range(20):
        stock.append({"sku": f"SKU{i}", "saldo": 50 - i, "custo": 20 + i})
    ar = []
    ap = []
    for i in range(20):
        ar.append({"due_date": base + timedelta(days=i), "amount": 500 + i * 50, "status": "aberto"})
        ap.append({"due_date": base + timedelta(days=i), "amount": 300 + i * 30, "status": "aberto"})

    return pd.DataFrame(orders), pd.DataFrame(stock), pd.DataFrame(ar), pd.DataFrame(ap)
