"""Stacked-frame poll panel.

Embeds an <img> tag and a small JS poll loop that fetches the scope's current
stacked frame from the backend's /api/imager/stacked.jpg endpoint (which talks
directly to the scope's :4800 channel — no bridge dependency).

Kept separate from `imaging.py` so neither file grows into a god-file.
"""

from __future__ import annotations

import streamlit as st


def render_stacked_image_panel(backend_port: int, refresh_seconds: int = 15) -> None:
    """Poll the backend's :4800-direct stacked-frame endpoint and refresh an <img>.

    The scope's native :4800 channel returns the latest stacked frame on demand
    via {"id": 23, "method": "get_stacked_img"}. The portal backend exposes that
    at GET /api/imager/stacked.jpg (204 when no frame is ready yet). This panel
    polls every N seconds with a cache-bust query param so the browser always
    re-fetches.
    """
    st.subheader("Stacked Frame")
    st.html(f"""
    <div id="sfp-container" style="background:#0a0a0a;border:1px solid #30363d;
                                   border-radius:8px;padding:8px;margin:4px 0;
                                   text-align:center;min-height:200px;">
        <img id="sfp-img"
             style="width:100%;max-height:70vh;object-fit:contain;display:none;"
             alt="Latest stacked frame from scope :4800" />
        <p id="sfp-status" style="color:#8b949e;padding:40px;margin:0;">
            Waiting for first stacked frame…
        </p>
    </div>
    <script>
    (function() {{
        var PORT = {int(backend_port)};
        var REFRESH_MS = {int(refresh_seconds) * 1000};
        var img = document.getElementById('sfp-img');
        var status = document.getElementById('sfp-status');
        if (!img || !status) return;
        var base = 'http://' + window.location.hostname + ':' + PORT + '/api/imager/stacked.jpg';

        function poll() {{
            fetch(base + '?ts=' + Date.now(), {{cache: 'no-store'}})
                .then(function(resp) {{
                    if (resp.status === 204) {{
                        status.textContent = 'No stacked frame yet — start a session to begin stacking.';
                        status.style.color = '#8b949e';
                        return null;
                    }}
                    if (!resp.ok) {{
                        status.textContent = 'Imager channel error (' + resp.status + ').';
                        status.style.color = '#f85149';
                        return null;
                    }}
                    return resp.blob();
                }})
                .then(function(blob) {{
                    if (!blob) return;
                    var url = URL.createObjectURL(blob);
                    var prev = img.src;
                    img.onload = function() {{
                        if (prev && prev.startsWith('blob:')) URL.revokeObjectURL(prev);
                    }};
                    img.src = url;
                    img.style.display = 'block';
                    status.textContent = '● Updated ' + new Date().toLocaleTimeString() +
                                          ' — refreshing every {int(refresh_seconds)}s';
                    status.style.color = '#3fb950';
                }})
                .catch(function(err) {{
                    status.textContent = 'Network error: ' + err.message;
                    status.style.color = '#f85149';
                }});
        }}

        poll();
        var interval = setInterval(poll, REFRESH_MS);
        window.addEventListener('beforeunload', function() {{ clearInterval(interval); }});
    }})();
    </script>
    """)
