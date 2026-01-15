from __future__ import annotations

import streamlit as st
from sqlalchemy.exc import IntegrityError

from models import Client
from services import admin_service
from services.auth_service import hash_password, logout
from services.bling_service import (
    BlingAuthError,
    exchange_code_for_token,
    force_refresh_token,
    friendly_token_icon,
    get_authorization_url,
    token_status,
)


def render_admin(session) -> None:
    st.title("Painel Administrativo")

    if st.button("Sair"):
        logout()
        st.rerun()

    clients = admin_service.list_clients(session)

    st.subheader("Clientes")
    table_rows = []
    for client in clients:
        status = token_status(client)
        plans = []
        if client.plan_sales:
            plans.append("📈")
        if client.plan_inventory:
            plans.append("📦")
        if client.plan_financial:
            plans.append("💰")
        table_rows.append(
            {
                "Nome": client.company_name,
                "Login": client.username,
                "Token": friendly_token_icon(status),
                "Planos": " ".join(plans) if plans else "-",
                "Logins": client.login_count,
            }
        )
    st.dataframe(table_rows, width="stretch")

    st.subheader("Cadastrar Cliente")
    with st.form("create_client"):
        company_name = st.text_input("Nome da Loja")
        username = st.text_input("Login (único)")
        password = st.text_input("Senha Provisória", type="password")
        bling_client_id = st.text_input("Bling Client ID")
        bling_client_secret = st.text_input("Bling Client Secret", type="password")
        if bling_client_id:
            auth_url = get_authorization_url(bling_client_id, state=username or "")
            st.markdown(f"[Autorizar no Bling]({auth_url})")
        auth_code = st.text_input("Code de autorização (OAuth)")
        st.markdown("**Planos Ativos**")
        plan_sales = st.checkbox("Ativar Módulo Vendas")
        plan_inventory = st.checkbox("Ativar Módulo Estoque")
        plan_financial = st.checkbox("Ativar Módulo Financeiro")
        submitted = st.form_submit_button("Salvar")

    if submitted:
        if not all([company_name, username, password, bling_client_id, bling_client_secret]):
            st.error("Preencha todos os campos obrigatórios.")
        else:
            try:
                access = None
                refresh = None
                expires_at = None
                if auth_code:
                    access, refresh, expires_at = exchange_code_for_token(
                        bling_client_id,
                        bling_client_secret,
                        auth_code,
                    )
                client = Client(
                    company_name=company_name,
                    username=username,
                    password_hash=hash_password(password),
                    bling_client_id=bling_client_id,
                    bling_client_secret=bling_client_secret,
                    access_token=access,
                    refresh_token=refresh,
                    token_expires_at=expires_at,
                    plan_sales=plan_sales,
                    plan_inventory=plan_inventory,
                    plan_financial=plan_financial,
                )
                admin_service.create_client(session, client)
                admin_service.log_action(session, client.id, "Cadastro de cliente")
                st.success("Cliente cadastrado com sucesso.")
            except IntegrityError:
                st.error("Login já existe. Escolha outro.")
            except BlingAuthError as exc:
                st.error(f"Falha na autenticação Bling: {exc}")
            except Exception as exc:
                st.error(f"Erro ao cadastrar cliente: {exc}")

    st.subheader("Editar Cliente")
    if clients:
        options = {f"{c.company_name} (id {c.id})": c for c in clients}
        selected = st.selectbox("Selecione", list(options.keys()))
        edit_client = options[selected]
        with st.form("edit_client"):
            bling_client_id = st.text_input("Bling Client ID", value=edit_client.bling_client_id)
            bling_client_secret = st.text_input(
                "Bling Client Secret", value=edit_client.bling_client_secret, type="password"
            )
            if bling_client_id:
                auth_url = get_authorization_url(bling_client_id, state=str(edit_client.id))
                st.markdown(f"[Autorizar no Bling]({auth_url})")
            auth_code = st.text_input("Code de autorização (OAuth)")
            new_password = st.text_input("Nova Senha (opcional)", type="password")
            st.markdown("**Planos**")
            plan_sales = st.checkbox("Vendas", value=edit_client.plan_sales)
            plan_inventory = st.checkbox("Estoque", value=edit_client.plan_inventory)
            plan_financial = st.checkbox("Financeiro", value=edit_client.plan_financial)
            is_active = st.checkbox("Cliente ativo", value=edit_client.is_active)
            save = st.form_submit_button("Salvar Alterações")

        if save:
            edit_client.bling_client_id = bling_client_id
            edit_client.bling_client_secret = bling_client_secret
            edit_client.plan_sales = plan_sales
            edit_client.plan_inventory = plan_inventory
            edit_client.plan_financial = plan_financial
            edit_client.is_active = is_active
            if new_password:
                edit_client.password_hash = hash_password(new_password)
            if auth_code:
                try:
                    access, refresh, expires_at = exchange_code_for_token(
                        edit_client.bling_client_id,
                        edit_client.bling_client_secret,
                        auth_code,
                    )
                    edit_client.access_token = access
                    edit_client.refresh_token = refresh
                    edit_client.token_expires_at = expires_at
                except BlingAuthError as exc:
                    st.error(f"Falha na autenticação: {exc}")
                    return
            admin_service.update_client(session, edit_client)
            admin_service.log_action(session, edit_client.id, "Atualização de cliente")
            st.success("Cliente atualizado.")
            st.rerun()

    st.subheader("Excluir Cliente")
    if clients:
        options = {f"{c.company_name} (id {c.id})": c for c in clients}
        selected_delete = st.selectbox("Cliente", list(options.keys()), key="delete_select")
        delete_client = options[selected_delete]
        confirm = st.checkbox("Confirmar exclusão definitiva")
        if st.button("Excluir Cliente"):
            if not confirm:
                st.error("Marque a confirmação para excluir.")
            else:
                admin_service.delete_client(session, delete_client.id)
                st.success("Cliente excluído.")
                st.rerun()

    st.subheader("Testar Conexão Bling")
    if clients:
        options = {f"{c.company_name} (id {c.id})": c for c in clients}
        selected_test = st.selectbox("Cliente", list(options.keys()), key="test_select")
        test_client = options[selected_test]
        if st.button("Testar Conexão"):
            try:
                force_refresh_token(test_client, session)
                admin_service.log_action(session, test_client.id, "Teste Bling")
                st.success("Conexão validada.")
            except BlingAuthError:
                st.error("Falha ao validar conexão. Token revogado ou inválido.")

    st.subheader("Primeira Autenticação Bling (OAuth)")
    if clients:
        options = {f"{c.company_name} (id {c.id})": c for c in clients}
        selected_auth = st.selectbox("Cliente", list(options.keys()), key="auth_select")
        auth_client = options[selected_auth]
        auth_url = get_authorization_url(auth_client.bling_client_id, state=str(auth_client.id))
        st.markdown(f"[Gerar autorização no Bling]({auth_url})")
        code = st.text_input("Cole o code retornado", key="auth_code")
        if st.button("Trocar code por token"):
            try:
                access, refresh, expires_at = exchange_code_for_token(
                    auth_client.bling_client_id,
                    auth_client.bling_client_secret,
                    code,
                )
                auth_client.access_token = access
                auth_client.refresh_token = refresh
                auth_client.token_expires_at = expires_at
                admin_service.update_client(session, auth_client)
                admin_service.log_action(session, auth_client.id, "OAuth inicial Bling")
                st.success("Tokens salvos com sucesso.")
            except BlingAuthError as exc:
                st.error(f"Falha na autenticação: {exc}")

    st.subheader("Auditoria")
    if clients:
        options = {f"{c.company_name} (id {c.id})": c for c in clients}
        selected_log = st.selectbox("Cliente", list(options.keys()), key="log_select")
        log_client = options[selected_log]
        logs = admin_service.get_logs(session, log_client.id)
        if logs:
            data = [{"Ação": log.action, "Data": log.timestamp} for log in logs]
            st.dataframe(data, width="stretch")
        else:
            st.info("Sem logs para este cliente.")
