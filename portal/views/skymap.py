"""Sky Map view — embedded Stellarium Web for visual planning.

Iframes stellarium-web.org so the user can browse the sky, search objects,
and pick targets in a familiar interface. No portal↔Stellarium wiring;
the user just reads off the object name and types it into GoTo.
"""

import streamlit as st


STELLARIUM_WEB_URL = "https://stellarium-web.org/"


def render_skymap():
    st.markdown(
        """
        <div style="margin-bottom:0.5rem">
            <h3 style="margin:0">&#x1F30C; Sky Map</h3>
            <p style="margin:0.25rem 0 0; opacity:0.75; font-size:0.9rem">
                Plan your session visually. Pick an object here, then type its
                name into <strong>GoTo</strong> to slew the scope.
                Powered by <a href="https://stellarium-web.org/" target="_blank"
                rel="noopener">stellarium-web.org</a>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.components.v1.iframe(
        src=STELLARIUM_WEB_URL,
        height=820,
        scrolling=False,
    )
