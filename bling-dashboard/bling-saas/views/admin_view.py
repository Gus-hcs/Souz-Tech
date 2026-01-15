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
    st.markdown(
        """
        <style>
            .admin-page {padding: 0 0 1rem 0;}
            .admin-header {text-align: center; margin: 0 0 1.5rem 0;}
            .admin-title {font-size: 2rem; font-weight: 800; color: #fafafa; letter-spacing: -0.5px;}
            .admin-subtitle {color: #9ca3af; margin-top: 0.35rem;}
            .card {background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1.25rem 1.35rem; box-shadow: 0 12px 40px rgba(0,0,0,0.25);} 
            .metric-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 0.75rem; margin-bottom: 1rem;}
            .metric {background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid #1f2937; border-radius: 10px; padding: 0.9rem 1rem;}
            .metric-title {color: #9ca3af; font-size: 0.9rem; margin-bottom: 0.15rem;}
            .metric-value {color: #fff; font-size: 1.4rem; font-weight: 700;}
            .badge {display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600;}
            .badge-ok {background: rgba(0,204,150,0.16); color: #34d399; border: 1px solid rgba(52,211,153,0.5);} 
            .badge-warn {background: rgba(245,158,11,0.18); color: #fbbf24; border: 1px solid rgba(251,191,36,0.5);} 
            .badge-error {background: rgba(239,68,68,0.16); color: #f87171; border: 1px solid rgba(248,113,113,0.55);} 
            .table-title {font-weight: 700; color: #e5e7eb; margin: 0.4rem 0 0.6rem 0;}
            .btn-logout button {background: linear-gradient(135deg, #ef4444, #b91c1c) !important; border: none !important;}
            .section-title {color: #e5e7eb; font-weight: 700; font-size: 1.1rem; margin-bottom: 0.75rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="admin-page">', unsafe_allow_html=True)

    col_h1, col_logout = st.columns([5, 1])
    with col_h1:
        st.markdown(
            '<div class="admin-header"><div class="admin-title">Painel Administrativo</div><div class="admin-subtitle">Gestão de clientes, tokens e planos</div></div>',
            unsafe_allow_html=True,
        )
    with col_logout:
        if st.button("Sair", key="admin_logout"):
            logout()
            st.rerun()

    clients = admin_service.list_clients(session)

    # Tabs organizadas
    tab_overview, tab_create, tab_edit, tab_tokens, tab_audit = st.tabs(
        ["Visão Geral", "Cadastrar", "Editar / Status", "Tokens & OAuth", "Auditoria"]
    )

    # Visão Geral
    with tab_overview:
        if not clients:
            st.info("Nenhum cliente cadastrado ainda.")
        else:
            total = len(clients)
            ativos = sum(1 for c in clients if c.is_active)
            inativos = total - ativos
            token_validos = sum(1 for c in clients if token_status(c) == "Valid")
            token_exp = total - token_validos

            st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
            for title, value in [
                ("Clientes", total),
                ("Ativos", ativos),
                ("Inativos", inativos),
                ("Tokens Válidos", token_validos),
                ("Tokens Pendentes/Exp.", token_exp),
            ]:
                st.markdown(
                    f"<div class='metric'><div class='metric-title'>{title}</div><div class='metric-value'>{value}</div></div>",
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)

            filtro = st.text_input("Filtrar por nome ou login", key="overview_filter")
            filtered = [
                c
                for c in clients
                if not filtro
                or filtro.lower() in (c.company_name or "").lower()
                or filtro.lower() in (c.username or "").lower()
            ]

            table_rows = []
            for client in filtered:
                status = token_status(client)
                badge = friendly_token_icon(status)
                plans = []
                if client.access_commander:
                    plans.append("🏠")
                if client.access_inventory:
                    plans.append("📦")
                if client.access_performance:
                    plans.append("💰")
                table_rows.append(
                    {
                        "Loja": client.company_name,
                        "Login": client.username,
                        "Token": badge,
                        "Módulos Ativos": " ".join(plans) if plans else "-",
                        "Logins": client.login_count,
                        "Ativo": "Sim" if client.is_active else "Não",
                    }
                )

            st.dataframe(table_rows, width="stretch")

    # Cadastro
    with tab_create:
        st.markdown('<div class="section-title">Cadastrar Cliente</div>', unsafe_allow_html=True)
        with st.form("create_client"):
            col_a, col_b = st.columns(2)
            with col_a:
                company_name = st.text_input("Nome da Loja")
                username = st.text_input("Login (único)")
                password = st.text_input("Senha Provisória", type="password")
            with col_b:
                bling_client_id = st.text_input("Bling Client ID")
                bling_client_secret = st.text_input("Bling Client Secret", type="password")
                if bling_client_id:
                    auth_url = get_authorization_url(bling_client_id, state=username or "")
                    st.markdown(f"[Autorizar no Bling]({auth_url})")
                auth_code = st.text_input("Code de autorização (OAuth)")

                st.markdown("**Permissões de Acesso (Planos)**")
                cols_plan = st.columns(3)
                access_commander = cols_plan[0].checkbox("Liberar Visão do Comandante", value=True)
                access_inventory = cols_plan[1].checkbox("Liberar Inteligência de Estoque")
                access_performance = cols_plan[2].checkbox("Liberar Performance de Vendas")
            submitted = st.form_submit_button("Salvar")

        if submitted:
            if not all([company_name, username, password, bling_client_id, bling_client_secret]):
                st.error("Preencha todos os campos obrigatórios.")
            else:
                try:
                    access = refresh = expires_at = None
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
                        access_commander=access_commander,
                        access_inventory=access_inventory,
                        access_performance=access_performance,
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

    # Edição e status
    with tab_edit:
        if not clients:
            st.info("Cadastre um cliente primeiro.")
        else:
            options = {f"{c.company_name} (id {c.id})": c for c in clients}
            selected = st.selectbox("Selecione o cliente", list(options.keys()))
            edit_client = options[selected]
            with st.form("edit_client"):
                col_a, col_b = st.columns(2)
                with col_a:
                    bling_client_id = st.text_input("Bling Client ID", value=edit_client.bling_client_id)
                    new_password = st.text_input("Nova Senha (opcional)", type="password")
                    is_active = st.checkbox("Cliente ativo", value=edit_client.is_active)
                with col_b:
                    bling_client_secret = st.text_input(
                        "Bling Client Secret", value=edit_client.bling_client_secret, type="password"
                    )
                    auth_code = st.text_input("Code de autorização (OAuth)")
                    st.markdown("**Permissões de Acesso (Planos)**")
                    access_commander = st.checkbox(
                        "Liberar Visão do Comandante", value=edit_client.access_commander
                    )
                    access_inventory = st.checkbox(
                        "Liberar Inteligência de Estoque", value=edit_client.access_inventory
                    )
                    access_performance = st.checkbox(
                        "Liberar Performance de Vendas", value=edit_client.access_performance
                    )

                save = st.form_submit_button("Salvar Alterações")

            if save:
                edit_client.bling_client_id = bling_client_id
                edit_client.bling_client_secret = bling_client_secret
                edit_client.access_commander = access_commander
                edit_client.access_inventory = access_inventory
                edit_client.access_performance = access_performance
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

        st.divider()
        if clients:
            options_del = {f"{c.company_name} (id {c.id})": c for c in clients}
            selected_delete = st.selectbox("Excluir cliente", list(options_del.keys()), key="delete_select")
            delete_client = options_del[selected_delete]
            confirm = st.checkbox("Confirmar exclusão definitiva")
            if st.button("Excluir Cliente", type="primary"):
                if not confirm:
                    st.error("Marque a confirmação para excluir.")
                else:
                    admin_service.delete_client(session, delete_client.id)
                    st.success("Cliente excluído.")
                    st.rerun()

    # Tokens e OAuth
    with tab_tokens:
        if not clients:
            st.info("Cadastre clientes para gerenciar tokens.")
        else:
            options_t = {f"{c.company_name} (id {c.id})": c for c in clients}
            selected_t = st.selectbox("Cliente", list(options_t.keys()), key="token_select")
            t_client = options_t[selected_t]

            cols_tok = st.columns(2)
            with cols_tok[0]:
                st.markdown('<div class="section-title">Testar Conexão</div>', unsafe_allow_html=True)
                if st.button("Testar Conexão", key="btn_test_conn"):
                    try:
                        force_refresh_token(t_client, session)
                        admin_service.log_action(session, t_client.id, "Teste Bling")
                        st.success("Conexão validada.")
                    except BlingAuthError:
                        st.error("Falha ao validar conexão. Token revogado ou inválido.")

            with cols_tok[1]:
                st.markdown('<div class="section-title">Primeira Autenticação OAuth</div>', unsafe_allow_html=True)
                auth_url = get_authorization_url(t_client.bling_client_id, state=str(t_client.id))
                st.markdown(f"[Gerar autorização no Bling]({auth_url})")
                code = st.text_input("Cole o code retornado", key="auth_code_new")
                if st.button("Trocar code por token", key="btn_exchange"):
                    try:
                        access, refresh, expires_at = exchange_code_for_token(
                            t_client.bling_client_id,
                            t_client.bling_client_secret,
                            code,
                        )
                        t_client.access_token = access
                        t_client.refresh_token = refresh
                        t_client.token_expires_at = expires_at
                        admin_service.update_client(session, t_client)
                        admin_service.log_action(session, t_client.id, "OAuth inicial Bling")
                        st.success("Tokens salvos com sucesso.")
                    except BlingAuthError as exc:
                        st.error(f"Falha na autenticação: {exc}")

    # Auditoria
    with tab_audit:
        if not clients:
            st.info("Nenhum cliente para auditar.")
        else:
            options_log = {f"{c.company_name} (id {c.id})": c for c in clients}
            selected_log = st.selectbox("Cliente", list(options_log.keys()), key="log_select")
            log_client = options_log[selected_log]
            logs = admin_service.get_logs(session, log_client.id)
            if logs:
                data = [{"Ação": log.action, "Data": log.timestamp} for log in logs]
                st.dataframe(data, width="stretch")
            else:
                st.info("Sem logs para este cliente.")

    st.markdown('</div>', unsafe_allow_html=True)
