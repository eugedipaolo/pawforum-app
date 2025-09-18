
import uuid
import requests
import streamlit as st
from authlib.integrations.requests_client import OAuth2Session
from db import create_user, verify_user, upsert_google_user

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = ["openid", "email", "profile"]


# -------- helpers comunes --------

def current_user() -> str | None:
    return st.session_state.get("user")


# -------- Google OAuth --------

def _get_google_conf():
    cfg = st.secrets.get("google_oauth", {})
    cid = cfg.get("client_id")
    csec = cfg.get("client_secret")
    redirect_uri = cfg.get("redirect_uri")
    if not cid or not csec or not redirect_uri:
        return None
    return cid, csec, redirect_uri


def build_google_login_url() -> str | None:
    vals = _get_google_conf()
    if not vals:
        return None
    client_id, client_secret, redirect_uri = vals
    state = uuid.uuid4().hex
    st.session_state["oauth_state"] = state
    client = OAuth2Session(client_id, client_secret, scope=GOOGLE_SCOPES, redirect_uri=redirect_uri)
    uri, _ = client.create_authorization_url(
        GOOGLE_AUTH_URL,
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="select_account",
    )
    return uri


def handle_google_callback():
    vals = _get_google_conf()
    if not vals:
        return None
    client_id, client_secret, redirect_uri = vals

    qp = st.query_params
    code = qp.get("code", [None])[0]
    state = qp.get("state", [None])[0]
    if not code or not state:
        return None
    if state != st.session_state.get("oauth_state"):
        st.error("Invalid OAuth state.")
        return None

    client = OAuth2Session(client_id, client_secret, scope=GOOGLE_SCOPES, redirect_uri=redirect_uri)
    token = client.fetch_token(GOOGLE_TOKEN_URL, code=code, grant_type="authorization_code")

    resp = requests.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {token['access_token']}"})
    if resp.status_code != 200:
        st.error("Failed to fetch Google user info.")
        return None
    info = resp.json()

    # upsert usuario
    username = upsert_google_user(info.get("sub"), info.get("email"), info.get("name"), info.get("picture"))
    st.session_state["user"] = username

    # limpia parametros query
    st.query_params
    return info


# -------- UI de autenticación --------

def auth_ui():
    from db import create_user, verify_user  # local import para evitar ciclos

    with st.sidebar.expander("Account", expanded=True):
        if current_user():
            st.success(f"Logged in as **{current_user()}**")
            if st.button("Log out", use_container_width=True):
                st.session_state.pop("user", None)
                st.rerun()
        else:
            tabs = st.tabs(["Log in", "Register"])
            with tabs[0]:
                u = st.text_input("Username", key="login_user")
                p = st.text_input("Password", type="password", key="login_pass")
                if st.button("Log in", use_container_width=True, key="login_btn"):
                    if verify_user(u, p):
                        st.session_state["user"] = u
                        st.success("Welcome back!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
            with tabs[1]:
                nu = st.text_input("Username", key="reg_user")
                np = st.text_input("Password", type="password", key="reg_pass")
                if st.button("Create account", use_container_width=True, key="reg_btn"):
                    err = create_user(nu, np)
                    if err:
                        st.error(err)
                    else:
                        st.success("Account created. You can log in now.")

            st.markdown("---")
            auth_url = build_google_login_url()
            if auth_url:
                st.markdown(
                    f'<a href="{auth_url}" target="_self" style="display:block;text-align:center;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:8px 12px;color:#111;text-decoration:none;">Continue with Google</a>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Configure Google OAuth in .streamlit/secrets.toml to enable Google login.")
