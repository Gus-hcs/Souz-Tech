import streamlit as st

from services.auth_service import login_user


LOGIN_CSS = """
<style>
    #MainMenu, footer, header {visibility: hidden;}
    div[data-testid="stAppViewContainer"] {background: #f4f6f9;}
    section.main {padding: 0 !important;}
    .block-container {padding-top: 0rem; padding-bottom: 0rem; height: 100vh;}
    .login-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        background: #f4f6f9;
        font-family: 'Inter', 'Roboto', sans-serif;
    }
    .login-card {
        background: white;
        padding: 2.5rem;
        border-radius: 16px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.08);
        width: 420px;
    }
    .login-title {
        font-size: 1.6rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
        color: #1F2937;
        text-align: center;
    }
</style>
"""


def render_login(session) -> None:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Bling Strategy Hub</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Login")
        password = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar")

    auth_error = st.session_state.pop("auth_error", None)
    if auth_error:
        st.error(auth_error)

    if submit:
        auth = login_user(username, password, session)
        if not auth:
            if auth_error:
                st.error(auth_error)
            else:
                st.error("Credenciais inválidas.")
        else:
            st.success("Login realizado.")
            st.rerun()

    st.markdown('</div></div>', unsafe_allow_html=True)
