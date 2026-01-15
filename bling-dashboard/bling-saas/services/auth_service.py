from __future__ import annotations

import os
from typing import Optional

import bcrypt
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models import Client, now_sp
from services.bling_service import BlingAuthError, ensure_valid_token


def load_env() -> None:
    load_dotenv(override=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def ensure_admin_env(env_path: str = ".env") -> None:
    load_env()
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass_hash = os.getenv("ADMIN_PASS_HASH", "")
    if admin_user and admin_pass_hash:
        return
    default_pass = os.getenv("ADMIN_PASS", "admin")
    generated_hash = hash_password(default_pass)
    os.environ["ADMIN_USER"] = admin_user or "admin"
    os.environ["ADMIN_PASS_HASH"] = generated_hash
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as file:
                lines = file.readlines()
            updated = []
            found_hash = False
            found_user = False
            for line in lines:
                if line.startswith("ADMIN_USER="):
                    updated.append(f"ADMIN_USER={admin_user or 'admin'}\n")
                    found_user = True
                elif line.startswith("ADMIN_PASS_HASH="):
                    updated.append(f"ADMIN_PASS_HASH={generated_hash}\n")
                    found_hash = True
                else:
                    updated.append(line)
            if not found_user:
                updated.append(f"ADMIN_USER={admin_user or 'admin'}\n")
            if not found_hash:
                updated.append(f"ADMIN_PASS_HASH={generated_hash}\n")
            with open(env_path, "w", encoding="utf-8") as file:
                file.writelines(updated)
    except OSError:
        pass


def get_admin_credentials() -> tuple[str, str]:
    load_env()
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass_hash = os.getenv("ADMIN_PASS_HASH", "")
    return admin_user, admin_pass_hash


def login_user(username: str, password: str, session: Session) -> Optional[dict]:
    admin_user, admin_pass_hash = get_admin_credentials()
    if username == admin_user and admin_pass_hash:
        if verify_password(password, admin_pass_hash):
            st.session_state["auth"] = {"role": "admin", "username": username}
            return st.session_state["auth"]
        return None

    client = session.query(Client).filter(Client.username == username).first()
    if not client:
        return None
    if not client.is_active:
        st.session_state["auth_error"] = "Acesso Suspenso"
        return None
    if not verify_password(password, client.password_hash):
        return None

    client.last_login = now_sp()
    client.login_count = (client.login_count or 0) + 1
    session.add(client)
    session.commit()

    try:
        ensure_valid_token(client, session)
    except BlingAuthError:
        st.session_state["token_error"] = "Token do Bling inválido ou revogado."

    st.session_state["auth"] = {
        "role": "client",
        "client_id": client.id,
        "username": username,
        "company_name": client.company_name,
    }
    return st.session_state["auth"]


def logout() -> None:
    st.session_state.pop("auth", None)
    st.session_state.pop("auth_error", None)
    st.session_state.pop("token_error", None)
