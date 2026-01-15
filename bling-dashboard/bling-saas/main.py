import streamlit as st

from models import Client, init_db, get_session_local
from services.auth_service import ensure_admin_env, logout
from views.admin_view import render_admin
from views.client_view import render_client
from views.login_view import render_login


def setup_page() -> None:
    st.set_page_config(page_title="Bling Strategy Hub", page_icon="📊", layout="wide")
    st.markdown(
        """
        <style>
            #MainMenu, footer, header {visibility: hidden;}
            .block-container {padding-top: 1rem;}
            body {background: #f4f6f9;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    ensure_admin_env()
    init_db()

    setup_page()

    SessionLocal = get_session_local()
    session = SessionLocal()

    auth = st.session_state.get("auth")
    if not auth:
        render_login(session)
        return

    role = auth.get("role")
    if role == "admin":
        render_admin(session)
    elif role == "client":
        client = session.query(Client).filter(Client.id == auth.get("client_id")).first()
        if not client:
            logout()
            st.error("Sessão inválida.")
            return
        if not client.is_active:
            logout()
            st.error("Acesso suspenso.")
            return
        render_client(session, client)
    else:
        logout()
        st.error("Sessão inválida.")


if __name__ == "__main__":
    main()
