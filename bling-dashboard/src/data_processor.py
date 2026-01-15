from __future__ import annotations

from typing import Dict, List

import duckdb
import pandas as pd


class DataProcessor:
    """ETL and business rules using DuckDB in-memory."""

    def __init__(self) -> None:
        self.con = duckdb.connect(database=":memory:")

    def _normalize_sales(self, sales: List[Dict]) -> pd.DataFrame:
        if not sales:
            return pd.DataFrame(
                columns=[
                    "id",
                    "data",
                    "numero",
                    "total",
                    "produto.id",
                    "produto.nome",
                    "quantidade",
                    "valor",
                ]
            )

        df_sales = pd.json_normalize(
            sales,
            record_path=["itens"],
            meta=[
                "id",
                "data",
                "numero",
                "total",
            ],
            errors="ignore",
        )

        return df_sales

    def process(self, sales: List[Dict], products: List[Dict], stock: List[Dict]) -> pd.DataFrame:
        df_sales = self._normalize_sales(sales)
        df_products = pd.DataFrame(products)
        df_stock = pd.DataFrame(stock)

        if df_products.empty:
            df_products = pd.DataFrame(columns=["id", "precoCusto", "nome"])
        if df_stock.empty:
            df_stock = pd.DataFrame(columns=["produto.id", "saldoFisico"])

        if df_sales.empty:
            return pd.DataFrame()

        self.con.register("sales", df_sales)
        self.con.register("products", df_products)
        self.con.register("stock", df_stock)

        query = """
            SELECT
                s.*,
                p.precoCusto AS preco_custo,
                st.saldoFisico AS saldo_fisico
            FROM sales s
            LEFT JOIN products p
                ON s."produto.id" = p.id
            LEFT JOIN stock st
                ON s."produto.id" = st."produto.id"
        """

        df = self.con.execute(query).fetchdf()

        df["valor_venda"] = pd.to_numeric(df.get("valor"), errors="coerce").fillna(0)
        df["preco_custo"] = pd.to_numeric(df.get("preco_custo"), errors="coerce").fillna(0)
        df["margem_unitaria"] = df["valor_venda"] - df["preco_custo"]

        df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
        df["quantidade"] = pd.to_numeric(df.get("quantidade"), errors="coerce").fillna(0)
        window_90 = df[df["data"] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=90))]

        daily_sales = (
            window_90.groupby(["produto.id", window_90["data"].dt.date])["quantidade"]
            .sum()
            .reset_index()
        )

        avg_daily = (
            daily_sales.groupby("produto.id")["quantidade"].mean().reset_index()
        )
        avg_daily.rename(columns={"quantidade": "media_venda_diaria"}, inplace=True)

        df = df.merge(avg_daily, on="produto.id", how="left")
        df["media_venda_diaria"] = df["media_venda_diaria"].fillna(0)

        df["saldo_fisico"] = pd.to_numeric(df.get("saldo_fisico"), errors="coerce").fillna(0)
        df["dias_cobertura"] = df.apply(
            lambda row: row["saldo_fisico"] / row["media_venda_diaria"]
            if row["media_venda_diaria"] > 0
            else None,
            axis=1,
        )

        return df

    def estoque_parado(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df_periodo = df[df["data"] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=90))]
        vendas_por_produto = (
            df_periodo.groupby("produto.id")["quantidade"].sum().reset_index()
        )
        vendas_por_produto.rename(columns={"quantidade": "qtde_vendida"}, inplace=True)

        df_parado = df.merge(vendas_por_produto, on="produto.id", how="left")
        df_parado["qtde_vendida"] = df_parado["qtde_vendida"].fillna(0)

        return df_parado[(df_parado["saldo_fisico"] > 0) & (df_parado["qtde_vendida"] == 0)]
