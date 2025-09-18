# PawForum — MVP SOLO con Streamlit (sin Flask)
# -------------------------------------------------
# Características:
# - UI estilo chat con canales (sidebar), mensajes y envío de texto/imagen
# - Persistencia local con SQLite (sin servidores adicionales)
# - Auto-refresh sencillo por JavaScript (reload cada N segundos)
# - Creación de canales desde la UI
# - Nickname por sesión (sidebar)
# - Subida de imágenes (guardadas en ./uploads)
# - **Paleta de colores visible en la página**
#
# Requisitos (requirements.txt):
# streamlit>=1.35.0
# pillow
#
# Ejecutar:
#   streamlit run streamlit_app.py

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import html

import streamlit as st
from PIL import Image

APP_TITLE = "PawForum"
DB_PATH = "pawforum.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Paleta de colores (modo oscuro)
PALETTE = {
    "Background": "#1f2937",   # gris azulado profundo
    "Surface": "#0f172a",      # aún más oscuro para paneles
    "Accent (Blue)": "#3b82f6",# azul brillante
    "Accent (Orange)": "#f59e0b", # naranja cálido
    "Text": "#e5e7eb",         # gris claro
    "Text strong": "#ffffff",   # blanco
}

DEFAULT_CHANNELS = [
    ("general", "General"),
    ("curiosities", "Curiosities"),
    ("tips-and-advice", "Tips & Advice"),
    ("adoptions", "Adoptions"),
    ("support-corner", "Support Corner"),
]

# --------------------------
# DB helpers
# --------------------------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                user TEXT NOT NULL,
                text TEXT,
                image_path TEXT,
                ts INTEGER NOT NULL,
                FOREIGN KEY(channel_id) REFERENCES channels(id)
            )
            """
        )
        # Seed default channels if empty
        cur.execute("SELECT COUNT(*) FROM channels")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO channels (id, name) VALUES (?, ?)", DEFAULT_CHANNELS)
        con.commit()


def list_channels() -> List[Dict[str, Any]]:
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM channels ORDER BY name ASC")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def insert_channel(channel_id: str, name: str) -> Optional[str]:
    channel_id = channel_id.strip().lower().replace(" ", "-")
    name = name.strip()
    if not channel_id or not name:
        return "Channel id and name are required."
    with get_conn() as con:
        try:
            con.execute("INSERT INTO channels (id, name) VALUES (?, ?)", (channel_id, name))
            con.commit()
        except sqlite3.IntegrityError:
            return "Channel id already exists."
    return None


def list_messages(channel_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT user, text, image_path, ts FROM messages WHERE channel_id = ? ORDER BY ts ASC LIMIT ?",
            (channel_id, limit),
        )
        rows = cur.fetchall()
    return [
        {"user": r[0], "text": r[1], "image_path": r[2], "ts": r[3]}
        for r in rows
    ]


def add_message(channel_id: str, user: str, text: str = "", image_path: Optional[str] = None):
    ts = int(time.time())
    with get_conn() as con:
        con.execute(
            "INSERT INTO messages (channel_id, user, text, image_path, ts) VALUES (?, ?, ?, ?, ?)",
            (channel_id, user, text, image_path, ts),
        )
        con.commit()


# --------------------------
# UI helpers
# --------------------------

def render_palette():
    #st.subheader("Brand colors")
    #st.caption("Palette used across the app")
    cols = st.columns(3)
    items = list(PALETTE.items())
    #for i, (label, hexv) in enumerate(items):
        #with cols[i % 3]:
            ### st.markdown(
            #    f"""
            #    <div style="border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:12px;background:#111827">
            #      <div style="height:56px;border-radius:8px;background:{hexv};"></div>
            #      <div style="font-size:12px;color:#e5e7eb;margin-top:8px">{label}</div>
            #      <div style="font-size:12px;color:#9ca3af">{hexv}</div>
            #    </div>
            #    """,
            #    unsafe_allow_html=True,
            #)


def sidebar_ui() -> Dict[str, Any]:
    st.sidebar.title(APP_TITLE)

    # Nickname
    st.sidebar.subheader("Your profile")
    if "nickname" not in st.session_state:
        st.session_state.nickname = "guest"
    st.session_state.nickname = st.sidebar.text_input(
        "Nickname", st.session_state.nickname, help="Shown next to your messages"
    )

    # Channels
    st.sidebar.subheader("Channels")
    chs = list_channels()
    ids = [c["id"] for c in chs]
    if "active_channel" not in st.session_state:
        st.session_state.active_channel = ids[0] if ids else "general"

    selected = st.sidebar.selectbox(
        "Select a channel",
        options=ids,
        format_func=lambda cid: next((f"#{c['id']} — {c['name']}" for c in chs if c['id']==cid), cid),
    )
    st.session_state.active_channel = selected

    with st.sidebar.expander("Create channel"):
        new_id = st.text_input("Channel id (e.g., cats-life)")
        new_name = st.text_input("Display name (e.g., Cats Life)")
        if st.button("Create"):
            err = insert_channel(new_id, new_name)
            if err:
                st.error(err)
            else:
                st.success(f"Channel #{new_id} created")
                st.rerun()

    # Auto refresh toggle
    st.sidebar.subheader("View options")
    refresh = st.sidebar.checkbox("Auto-refresh", value=True, help="Update messages every few seconds")
    interval_ms = st.sidebar.slider("Refresh every (seconds)", 2, 20, 4) * 1000
    return {"refresh": refresh, "interval_ms": interval_ms}


def message_bubble(msg: Dict[str, Any], nickname: str):
    ts = datetime.fromtimestamp(msg["ts"]).strftime("%H:%M") if msg.get("ts") else ""
    is_self = (msg.get("user") or "") == (nickname or "")
    bubble_class = "bubble self" if is_self else "bubble"
    st.markdown(f"<div class='{bubble_class}'>", unsafe_allow_html=True)
    st.markdown(
        f"<div><strong style='color: var(--text-strong)'>{html.escape(msg['user'])}</strong>"
        f" <span class='timestamp'>· {ts}</span></div>",
        unsafe_allow_html=True,
    )
    if msg.get("text"):
        st.markdown(f"<div style='margin-top:4px;color:var(--text)'>" + html.escape(msg["text"]) + "</div>", unsafe_allow_html=True)
    if msg.get("image_path"):
        try:
            Image.open(msg["image_path"])  # verify
            st.image(msg["image_path"], use_column_width=True)
        except Exception:
            st.caption("(Image not available)")
    st.markdown("</div>", unsafe_allow_html=True)


def composer_ui(active_channel: str, nickname: str):
    st.divider()
    col1, col2 = st.columns([4,1])

    with col1:
        text = st.text_input(f"Message #{active_channel}", key="msg_input", placeholder="Type your message…")
        uploaded = st.file_uploader(
            "Attach an image (optional)",
            type=["png","jpg","jpeg","gif"],
            accept_multiple_files=False,
        )
    with col2:
        st.write("")
        st.write("")
        send = st.button("Send", use_container_width=True)

    if send:
        image_path = None
        if uploaded is not None:
            safe_name = f"{int(time.time())}_{uploaded.name.replace(' ', '_')}"
            out_path = UPLOAD_DIR / safe_name
            with open(out_path, "wb") as f:
                f.write(uploaded.getbuffer())
            image_path = str(out_path)
        text_val = (text or "").strip()
        if not text_val and not image_path:
            st.warning("Write a message or attach an image.")
        else:
            add_message(active_channel, nickname or "anon", text_val, image_path)
            st.session_state.msg_input = ""
            st.rerun()


# --------------------------
# App
# --------------------------

def main():
    st.set_page_config(page_title="PawForum", page_icon="💬", layout="wide")
    init_db()

    # Global styles using the brand palette
    st.markdown(f"""
    <style>
      :root {{
        --bg: {PALETTE['Surface']};
        --panel: {PALETTE['Background']};
        --accent: {PALETTE['Accent (Blue)']};
        --accent2: {PALETTE['Accent (Orange)']};
        --text: {PALETTE['Text']};
        --text-strong: {PALETTE['Text strong']};
      }}
      html, body, [data-testid="stAppViewContainer"] {{ background: var(--bg); color: var(--text); }}
      [data-testid="stSidebar"] {{ background: var(--panel); }}
      .bubble {{
        background: var(--panel);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 10px 12px;
        margin-bottom: 8px;
      }}
      .bubble.self {{
        border-color: var(--accent);
        box-shadow: 0 0 0 1px var(--accent) inset;
      }}
      .timestamp {{ color: #9ca3af; font-size: 12px; }}
      .stButton>button {{
        background: var(--accent); color: #fff; border: 0; border-radius: 10px; padding: 8px 14px;
      }}
     

    /* Inputs: estilo base */
    input[type="text"], textarea, .stTextInput > div > div > input {{
        background: var(--panel) !important;
        color: var(--text) !important;
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        padding: 8px 10px;
        transition: border-color .2s ease, box-shadow .2s ease;
    }}

    /* Inputs: foco con azul de la burbuja */
    input[type="text"]:focus,
    textarea:focus,
    .stTextInput > div > div > input:focus {{
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent) !important;
        outline: none !important;
    }}

    /* Accesibilidad: focus visible */
    input[type="text"]:focus-visible,
    textarea:focus-visible,
    .stTextInput > div > div > input:focus-visible {{
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent) !important;
        outline: none !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    opts = sidebar_ui()

    # Header
    st.markdown(f"### {APP_TITLE}")
    st.caption("A friendly forum for animal lovers — share, learn, and connect.")

    # Paleta visible
    render_palette()
    st.divider()

    active = st.session_state.active_channel
    nickname = st.session_state.nickname

    # Messages list
    placeholder = st.empty()

    def render_messages():
        with placeholder.container():
            msgs = list_messages(active)
            for m in msgs:
                message_bubble(m, nickname)

    render_messages()

    # Lightweight polling para auto-refresh (recarga completa)
    if opts["refresh"]:
        st.caption(f"Auto-refresh: every {opts['interval_ms']//1000}s")
        st.markdown(
            f"""
            <script>
              setTimeout(() => {{ window.location.reload(); }}, {opts['interval_ms']});
            </script>
            """,
            unsafe_allow_html=True,
        )

    composer_ui(active, nickname)


if __name__ == "__main__":
    main()
