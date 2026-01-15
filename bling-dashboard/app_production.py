from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


# -----------------------------
# Config & Styling
# -----------------------------
load_dotenv()

st.set_page_config(page_title="E-commerce Strategy Hub", layout="wide")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"]  {
    font-family: 'Inter', sans-serif;
}

/* Hide Streamlit default menu and footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* App background */
.stApp {
    background-color: #f0f2f6;
}

/* Cards for metrics, charts and tables */
div[data-testid="stMetric"],
div[data-testid="stPlotlyChart"],
div[data-testid="stDataFrame"] {
    background: #ffffff;
    padding: 16px 18px;
    border-radius: 12px;
    box-shadow: 0 6px 14px rgba(0,0,0,0.06);
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #ffffff;
}

/* Button styling */
.stButton>button {
    border-radius: 10px;
    padding: 0.5rem 1rem;
    font-weight: 600;
}

/* Header title */
.app-title {
    font-size: 1.6rem;
    font-weight: 700;
    margin-bottom: 0.4rem;
}

.sidebar-logo {
    font-size: 1.1rem;
    font-weight: 700;
    padding: 0.6rem 0;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------
# Auth / Token Handling
# -----------------------------
@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_in: int
    expiry_timestamp: int


class BlingAuth:
    """Handle OAuth2 token lifecycle for Bling API v3."""

    def __init__(self, token_path: Path) -> None:
        self.client_id = os.getenv("BLING_CLIENT_ID")
        self.client_secret = os.getenv("BLING_CLIENT_SECRET")
        self.redirect_uri = os.getenv("BLING_REDIRECT_URI")
        self.token_path = token_path

        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Missing BLING_CLIENT_ID or BLING_CLIENT_SECRET in .env"
            )

    def _read_tokens(self) -> TokenData:
        if not self.token_path.exists():
            raise FileNotFoundError(
                "tokens.json not found. Provide initial OAuth2 token first."
            )

        with self.token_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        return TokenData(
            access_token=raw.get("access_token", ""),
            refresh_token=raw.get("refresh_token", ""),
            expires_in=int(raw.get("expires_in", 0)),
            expiry_timestamp=int(raw.get("expiry_timestamp", 0)),
        )

    def _write_tokens(self, data: TokenData) -> None:
        payload = {
            "access_token": data.access_token,
            "refresh_token": data.refresh_token,
            "expires_in": data.expires_in,
            "expiry_timestamp": data.expiry_timestamp,
        }
        with self.token_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _refresh_token(self, refresh_token: str) -> TokenData:
        url = "https://www.bling.com.br/Api/v3/oauth/token"
        payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        response = requests.post(
            url,
            data=payload,
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        response.raise_for_status()
        body: Dict[str, Any] = response.json()

        expires_in = int(body.get("expires_in", 0))
        expiry_timestamp = int(time.time()) + expires_in - 60

        return TokenData(
            access_token=body.get("access_token", ""),
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in=expires_in,
            expiry_timestamp=expiry_timestamp,
        )

    def get_valid_token(self) -> str:
        tokens = self._read_tokens()

        if not tokens.access_token or not tokens.refresh_token:
            raise RuntimeError(
                "tokens.json is missing access_token or refresh_token."
            )

        now = int(time.time())
        if tokens.expiry_timestamp <= now:
            refreshed = self._refresh_token(tokens.refresh_token)
            self._write_tokens(refreshed)
            return refreshed.access_token

        return tokens.access_token


class BlingClient:
    """HTTP client for Bling API v3 with pagination and rate limiting."""

    def __init__(self, token_path: Path) -> None:
        self.auth = BlingAuth(token_path)
        self.base_url = "https://www.bling.com.br/Api/v3"

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = self.auth.get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}{endpoint}"

        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            response.raise_for_status()
        response.raise_for_status()
        return response.json()

    def get_all_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        page = 1
        params = params.copy() if params else {}

        while True:
            params.update({"pagina": page})
            data = self._get(endpoint, params)

            items = data.get("data", []) if isinstance(data, dict) else []
            if not items:
                break

            all_items.extend(items)
            page += 1
            time.sleep(0.4)  # rate limit 3 req/s

        return all_items


# -----------------------------
# Data Processing
# -----------------------------
class DataProcessor:
    """ETL and KPI calculation using DuckDB in-memory."""

    def __init__(self) -> None:
        self.con = duckdb.connect(database=":memory:")

    @staticmethod
    def _normalize_sales(sales: List[Dict]) -> pd.DataFrame:
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
                    "canalVenda",
                ]
            )

        df_sales = pd.json_normalize(
            sales,
            record_path=["itens"],
            meta=["id", "data", "numero", "total", "canalVenda", "loja.nome"],
            errors="ignore",
        )
        return df_sales

    @staticmethod
    def _normalize_products(products: List[Dict]) -> pd.DataFrame:
        df = pd.json_normalize(products, errors="ignore")
        if df.empty:
            return pd.DataFrame(columns=["id", "precoCusto", "nome"])
        return df

    @staticmethod
    def _normalize_stock(stock: List[Dict]) -> pd.DataFrame:
        df = pd.json_normalize(stock, errors="ignore")
        if df.empty:
            return pd.DataFrame(columns=["produto.id", "saldoFisico"])
        return df

    @staticmethod
    def _derive_channel(df: pd.DataFrame) -> pd.Series:
        candidates = [
            "canalVenda",
            "canalVenda.descricao",
            "canalVenda.nome",
            "loja.nome",
            "loja",
            "marketplace",
        ]
        for col in candidates:
            if col in df.columns:
                return df[col].fillna("Indefinido")
        return pd.Series(["Indefinido"] * len(df), index=df.index)

    @staticmethod
    def _derive_product_name(df: pd.DataFrame) -> pd.Series:
        candidates = ["produto.nome", "produto.descricao", "descricao"]
        for col in candidates:
            if col in df.columns:
                return df[col].fillna("Produto")
        return pd.Series(["Produto"] * len(df), index=df.index)

    def process(self, sales: List[Dict], products: List[Dict], stock: List[Dict]) -> pd.DataFrame:
        df_sales = self._normalize_sales(sales)
        df_products = self._normalize_products(products)
        df_stock = self._normalize_stock(stock)

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
        df["produto_nome"] = self._derive_product_name(df)
        df["canal_venda"] = self._derive_channel(df)

        df["valor_venda"] = pd.to_numeric(df.get("valor"), errors="coerce").fillna(0)
        df["quantidade"] = pd.to_numeric(df.get("quantidade"), errors="coerce").fillna(0)
        df["preco_custo"] = pd.to_numeric(df.get("preco_custo"), errors="coerce").fillna(0)
        df["saldo_fisico"] = pd.to_numeric(df.get("saldo_fisico"), errors="coerce").fillna(0)

        df["item_total"] = df["valor_venda"] * df["quantidade"]
        df["margem_unitaria"] = df["valor_venda"] - df["preco_custo"]
        df["margem_total"] = df["margem_unitaria"] * df["quantidade"]

        df["data"] = pd.to_datetime(df.get("data"), errors="coerce")

        # Average daily sales (last 90 days)
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

        df["dias_cobertura"] = df.apply(
            lambda row: row["saldo_fisico"] / row["media_venda_diaria"]
            if row["media_venda_diaria"] > 0
            else None,
            axis=1,
        )

        return df

    @staticmethod
    def estoque_parado(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
        if df.empty:
            return df

        df_periodo = df[(df["data"] >= start) & (df["data"] <= end)]
        vendas_por_produto = (
            df_periodo.groupby("produto.id")["quantidade"].sum().reset_index()
        )
        vendas_por_produto.rename(columns={"quantidade": "qtde_vendida"}, inplace=True)

        df_parado = df.merge(vendas_por_produto, on="produto.id", how="left")
        df_parado["qtde_vendida"] = df_parado["qtde_vendida"].fillna(0)

        return df_parado[(df_parado["saldo_fisico"] > 0) & (df_parado["qtde_vendida"] == 0)]


# -----------------------------
# Utility Functions
# -----------------------------
APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "").strip()
STORE_NAME = os.getenv("STORE_NAME", "Sua Loja")
BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "tokens.json"


def _hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def _check_login() -> None:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return

    st.markdown("<div class='app-title'>E-commerce Strategy Hub</div>", unsafe_allow_html=True)
    st.subheader("Login")
    password = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if not APP_PASSWORD_HASH:
            st.error("APP_PASSWORD_HASH não configurado no .env")
            st.stop()
        if _hash_password(password) == APP_PASSWORD_HASH:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Senha inválida")

    st.stop()


@st.cache_data(ttl=3600)
def fetch_bling_data() -> Tuple[List[Dict], List[Dict], List[Dict]]:
    client = BlingClient(TOKEN_PATH)
    sales = client.get_all_data("/pedidos/vendas")
    products = client.get_all_data("/produtos")
    stock = client.get_all_data("/estoques/saldos")
    return sales, products, stock


def _safe_date_range() -> Tuple[date, date]:
    end = date.today()
    start = end.fromordinal(end.toordinal() - 90)
    return start, end


# -----------------------------
# App
# -----------------------------
_check_login()

st.sidebar.markdown("<div class='sidebar-logo'>E-commerce Strategy Hub</div>", unsafe_allow_html=True)
st.sidebar.caption(f"{STORE_NAME}")

if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

start_default, end_default = _safe_date_range()
periodo = st.sidebar.date_input(
    "Período",
    value=(start_default, end_default),
)

header_left, header_right = st.columns([3, 1])
with header_left:
    saudacao = "Bom dia" if datetime.now().hour < 12 else "Boa tarde"
    st.markdown(
        f"<div class='app-title'>{saudacao}, {STORE_NAME}</div>",
        unsafe_allow_html=True,
    )

with header_right:
    if st.button("Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

try:
    with st.spinner("Carregando dados do ERP..."):
        raw_sales, raw_products, raw_stock = fetch_bling_data()
except Exception:
    st.error("Falha na conexão com o ERP")
    st.stop()

processor = DataProcessor()
df_items = processor.process(raw_sales, raw_products, raw_stock)

if df_items.empty:
    st.info("Sem dados para o período selecionado.")
    st.stop()

# Date filter
if isinstance(periodo, tuple) and len(periodo) == 2:
    start_date = pd.to_datetime(periodo[0])
    end_date = pd.to_datetime(periodo[1])
else:
    start_date = pd.to_datetime(start_default)
    end_date = pd.to_datetime(end_default)

mask = (df_items["data"] >= start_date) & (df_items["data"] <= end_date)
df_filtered = df_items[mask]

# Marketplace filter
marketplaces = sorted(df_filtered["canal_venda"].dropna().unique().tolist())
marketplace = st.sidebar.selectbox("Canal de Venda", ["Todos"] + marketplaces)
if marketplace != "Todos":
    df_filtered = df_filtered[df_filtered["canal_venda"] == marketplace]

# KPIs
revenue_total = df_filtered["item_total"].sum()
margin_total = df_filtered["margem_total"].sum()
margin_pct = (margin_total / revenue_total * 100) if revenue_total else 0

order_count = df_filtered["id"].nunique()
ticket_medio = (revenue_total / order_count) if order_count else 0

estoque_parado = processor.estoque_parado(df_items, start_date, end_date)
estoque_parado_valor = (estoque_parado["saldo_fisico"] * estoque_parado["preco_custo"]).sum()

# Tabs
aba_exec, aba_estoque, aba_fin = st.tabs([
    "Dashboard Executivo",
    "Gestão de Estoque",
    "Finanças",
])

with aba_exec:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Receita", f"R$ {revenue_total:,.2f}")
    m2.metric("Ticket Médio", f"R$ {ticket_medio:,.2f}")
    m3.metric("Margem %", f"{margin_pct:.2f}%")
    m4.metric("Estoque Parado R$", f"R$ {estoque_parado_valor:,.2f}")

    col_line, col_donut = st.columns([2, 1])

    trend = (
        df_filtered.groupby(df_filtered["data"].dt.date)["item_total"]
        .sum()
        .reset_index()
        .rename(columns={"data": "dia", "item_total": "receita"})
    )
    fig_line = px.line(
        trend,
        x="dia",
        y="receita",
        title="Tendência de Venda",
        markers=True,
    )
    col_line.plotly_chart(fig_line, use_container_width=True)

    share = (
        df_filtered.groupby("canal_venda")["item_total"]
        .sum()
        .reset_index()
        .rename(columns={"item_total": "receita"})
    )
    fig_donut = px.pie(
        share,
        values="receita",
        names="canal_venda",
        hole=0.5,
        title="Share de Canais",
    )
    col_donut.plotly_chart(fig_donut, use_container_width=True)

with aba_estoque:
    st.subheader("Risco de Ruptura")
    risco = df_filtered[df_filtered["dias_cobertura"].notna()].copy()
    risco["risco_pct"] = (risco["dias_cobertura"].clip(0, 30) / 30 * 100).fillna(0)
    risco = risco.sort_values("dias_cobertura")

    st.dataframe(
        risco[[
            "produto.id",
            "produto_nome",
            "saldo_fisico",
            "media_venda_diaria",
            "dias_cobertura",
            "risco_pct",
        ]],
        column_config={
            "produto.id": st.column_config.TextColumn("SKU"),
            "produto_nome": st.column_config.TextColumn("Produto"),
            "saldo_fisico": st.column_config.NumberColumn("Saldo"),
            "media_venda_diaria": st.column_config.NumberColumn("Venda Média/Dia"),
            "dias_cobertura": st.column_config.NumberColumn("Dias de Cobertura"),
            "risco_pct": st.column_config.ProgressColumn(
                "Risco",
                min_value=0,
                max_value=100,
                format="%d%%",
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

with aba_fin:
    st.subheader("Cascata Financeira")

    custos = df_filtered["preco_custo"].mul(df_filtered["quantidade"]).sum()
    margem = revenue_total - custos

    fig_waterfall = go.Figure(
        go.Waterfall(
            name="",
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Faturamento", "Custos", "Margem Bruta"],
            y=[revenue_total, -custos, margem],
            text=[
                f"R$ {revenue_total:,.2f}",
                f"R$ {custos:,.2f}",
                f"R$ {margem:,.2f}",
            ],
        )
    )
    fig_waterfall.update_layout(title="Faturamento → Custos → Margem Bruta")
    st.plotly_chart(fig_waterfall, use_container_width=True)
