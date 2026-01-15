import streamlit as st
from services.auth_service import login_user

def render_login(session) -> None:
    # --- CSS PROFISSIONAL E UNIFORME ---
    LOGIN_CSS = """
    <style>
        /* 1. RESET GERAL E BACKGROUND */
        header, footer {visibility: hidden;}
        
        [data-testid="stAppViewContainer"] {
            background-color: #0E1117;
            background-image: radial-gradient(circle at 50% 0%, #1c2336 0%, #0E1117 70%);
            background-attachment: fixed;
        }

        /* 2. POSICIONAMENTO DO CONTAINER */
        .block-container {
            padding-top: 3rem !important;
            max-width: 600px !important; 
        }

        /* 3. CARD DE LOGIN */
        [data-testid="stForm"] {
            background-color: #161920;
            border: 1px solid #2D333F;
            border-radius: 12px;
            padding: 3rem 2.5rem !important;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
            margin-top: 2vh;
        }

        /* 4. TIPOGRAFIA */
        .login-header-emoji {
            font-size: 3rem;
            text-align: center;
            margin-bottom: 0.5rem;
            display: block;
        }
        .login-title {
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 1.8rem;
            font-weight: 700;
            color: #FFFFFF;
            text-align: center;
            margin-bottom: 0.25rem;
            letter-spacing: -0.02em;
        }
        .login-subtitle {
            font-family: 'Inter', sans-serif;
            font-size: 0.95rem;
            color: #8B949E;
            text-align: center;
            margin-bottom: 2.5rem;
        }

        /* 5. INPUTS - CORREÇÃO TOTAL DO FUNDO */
        
        div[data-testid="stTextInput"] {
            margin-bottom: 1.2rem !important;
        }

        /* Container Externo (A forma arredondada cinza) */
        div[data-baseweb="input"] {
            background-color: #21262D !important; /* Cor única de fundo */
            border: none !important; 
            border-radius: 8px !important;
            height: 55px !important;
            padding: 0 16px !important;
            align-items: center !important;
            transition: all 0.2s ease;
        }

        /* CORREÇÃO AQUI: Força TODOS os elementos internos a serem transparentes */
        div[data-baseweb="input"] > div,       /* Wrapper direto */
        div[data-baseweb="base-input"],        /* O container que aparece ao digitar */
        input[class*="st-"] {                  /* O campo de texto em si */
            background-color: transparent !important;
            border: none !important;
            color: #E6EDF3 !important;
            box-shadow: none !important; /* Remove sombras internas */
        }

        /* Ajuste fino para o texto digitado */
        div[data-baseweb="input"] input {
            background-color: transparent !important;
            color: #E6EDF3 !important;
            padding: 0 !important;
            font-size: 1rem !important;
            caret-color: #00CC96 !important; /* Cor do cursor piscando */
        }

        /* Efeito de Foco no Container Externo */
        div[data-baseweb="input"]:focus-within {
            background-color: #262c36 !important;
            box-shadow: 0 0 0 2px rgba(0, 204, 150, 0.3) !important;
        }
        
        /* Labels */
        div[data-testid="stTextInput"] label {
            font-size: 0.9rem;
            color: #E6EDF3;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }

        /* 6. BOTÃO DE LOGIN */
        div[data-testid="stFormSubmitButton"] {
            margin-top: 2rem;
        }
        div[data-testid="stFormSubmitButton"] button {
            background: #00CC96 !important;
            color: #0E1117 !important;
            border: none !important;
            height: 55px !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            border-radius: 8px !important;
            width: 100% !important;
            transition: opacity 0.2s;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            opacity: 0.9;
        }

        /* 7. LINKS E RODAPÉ */
        .forgot-pass {
            text-align: right;
            margin-top: -0.8rem;
            margin-bottom: 0.5rem;
        }
        .forgot-pass a {
            color: #00CC96;
            font-size: 0.85rem;
            text-decoration: none;
            opacity: 0.8;
            transition: opacity 0.2s;
        }
        .forgot-pass a:hover {
            opacity: 1;
        }
        
        .login-footer {
            margin-top: 3rem;
            text-align: center;
            font-size: 0.8rem;
            color: #484F58;
        }

        div[data-testid="stAlert"] {
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1.5rem;
        }
    </style>
    """
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    # --- ESTRUTURA VISUAL ---
    
    # Header
    st.markdown('<div class="login-header-emoji">🏢</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Bling Strategy Hub</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Dashboard Inteligente para Sua Loja</div>', unsafe_allow_html=True)

    # Mensagens de Erro
    auth_error = st.session_state.pop("auth_error", None)
    if auth_error:
        st.error(f"{auth_error}", icon="🚫")

    # --- FORMULÁRIO ---
    with st.form("login_form", clear_on_submit=False):
        
        username = st.text_input("Usuário", placeholder="Digite seu usuário", key="user_input")
        password = st.text_input("Senha", type="password", placeholder="Digite sua senha", key="pass_input")
        
        st.markdown('<div class="forgot-pass"><a href="#">Esqueci minha senha</a></div>', unsafe_allow_html=True)

        submit = st.form_submit_button("Acessar Painel")

        if submit:
            if not username or not password:
                st.warning("Por favor, preencha seus dados de acesso.")
            else:
                auth = login_user(username, password, session)
                
                if not auth:
                    st.error("Usuário ou senha incorretos.")
                else:
                    st.toast("Login realizado com sucesso!", icon="✅")
                    st.rerun()

    # --- RODAPÉ ---
    st.markdown(
        '<div class="login-footer">© 2026 <strong>Souz Tech</strong> • Bling Intelligence System</div>', 
        unsafe_allow_html=True
    )