from __future__ import annotations

import streamlit as st
import pandas as pd

from bling_client import BlingClient
from data_processor import DataProcessor


st.set_page_config(layout="wide", page_title="Bling Intelligence Dashboard")


def _load_data() -> pd.DataFrame:
    client = BlingClient()
    processor = DataProcessor()

    sales = client.get_all_data("/pedidos/vendas")
    products = client.get_all_data("/produtos")
    stock = client.get_all_data("/estoques/saldos")

    df = processor.process(sales, products, stock)
    return df


if "data" not in st.session_state:
    st.session_state["data"] = pd.DataFrame()

st.sidebar.title("Controles")
if st.sidebar.button("Atualizar Dados"):
    try:
        st.session_state["data"] = _load_data()
        st.sidebar.success("Dados atualizados com sucesso!")
    except Exception as exc:  # noqa: BLE001 - surface error to UI
        st.sidebar.error(f"Erro ao atualizar dados: {exc}")


df_data: pd.DataFrame = st.session_state["data"]

st.title("Dashboard de Inteligência Bling")

if df_data.empty:
    st.info("Clique em 'Atualizar Dados' para carregar informações do Bling.")
    st.stop()

faturamento_total = df_data["valor_venda"].sum()
lucro_estimado = df_data["margem_unitaria"].sum()
margem_pct = (lucro_estimado / faturamento_total * 100) if faturamento_total else 0

col1, col2, col3 = st.columns(3)
col1.metric("Faturamento Total", f"R$ {faturamento_total:,.2f}")
col2.metric("Lucro Estimado", f"R$ {lucro_estimado:,.2f}")
col3.metric("Margem %", f"{margem_pct:.2f}%")

aba_risco, aba_oportunidade = st.tabs(["Risco", "Oportunidade"])

with aba_risco:
    risco = df_data[df_data["dias_cobertura"].notna()].sort_values("dias_cobertura")
    st.subheader("Risco de Ruptura")
    st.dataframe(
        risco[["produto.id", "produto.nome", "saldo_fisico", "media_venda_diaria", "dias_cobertura"]]
    )

with aba_oportunidade:
    processor = DataProcessor()
    parado = processor.estoque_parado(df_data)
    st.subheader("Estoque Parado")
    st.dataframe(
        parado[["produto.id", "produto.nome", "saldo_fisico", "qtde_vendida"]]
    )
