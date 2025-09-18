import streamlit as st
from db import init_db
from auth import handle_google_callback
from ui import inject_styles, render_palette, sidebar_ui, render_chat, composer_ui

APP_TITLE = "PawForum"


def main():
    import sys, streamlit as st
    st.caption(f"Build: streamlit_app.py → app.main | Python {sys.version.split()[0]}")
    st.set_page_config(page_title=APP_TITLE, page_icon="💬", layout="wide")
    init_db()

    # Procesa callback Google (?code&state)
    info = handle_google_callback()
    if info and not st.session_state.get("_google_processed"):
        st.session_state["_google_processed"] = True
        st.rerun()

    inject_styles()

    # Sidebar (auth + canales + opciones)
    opts, active_channel, username = sidebar_ui(APP_TITLE)

    # Header
    st.markdown(f"### {APP_TITLE}")
    st.caption("A friendly forum for animal lovers — share, learn, and connect.")

    # Paleta visible
  
    st.divider()

    # Chat
    render_chat(active_channel, username)

    # Auto-refresh simple
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

    composer_ui(active_channel, username)


if __name__ == "__main__":
    main()