"""Settings configuration page."""
import streamlit as st
import toml
from pathlib import Path


def render_settings(config, alpaca=None, stellarium=None):
    """Render settings page. Config can be a Config object or raw dict."""
    st.header("\u2699\ufe0f Settings")

    # Support both Config object and raw dict
    def _get(section, key, default=None):
        if hasattr(config, '_data'):
            return config._data.get(section, {}).get(key, default)
        elif isinstance(config, dict):
            return config.get(section, {}).get(key, default)
        return default

    def _set(section, key, value):
        if hasattr(config, '_data'):
            config._data.setdefault(section, {})[key] = value
        elif isinstance(config, dict):
            config.setdefault(section, {})[key] = value

    with st.form("settings_form"):
        st.subheader("Seestar Connection")
        st.caption("Configure the network connection to your Seestar S50 telescope. "
                   "The phone app must connect first to enable ALPACA.")
        ip = st.text_input("Seestar IP Address",
                           value=_get("seestar", "ip_address", "192.168.0.132"),
                           help="Wi-Fi IP address of the Seestar S50. Find it in your "
                                "router's DHCP table or the ZWO app's network info.")
        port = st.number_input("ALPACA Port",
                               value=_get("seestar", "alpaca_port", 32323),
                               min_value=1, max_value=65535,
                               help="ASCOM ALPACA REST API port. The Seestar S50 "
                                    "uses 32323 by default. Do not change unless "
                                    "you have a custom configuration.")
        auto_connect = st.checkbox("Auto-connect on startup",
                                   value=_get("seestar", "auto_connect", True),
                                   help="Automatically connect to all 5 ALPACA devices "
                                        "(telescope, camera, focuser, filter wheel, switch) "
                                        "when the app starts.")

        st.subheader("Stellarium")
        st.caption("Connect to Stellarium's Remote Control plugin for visual target "
                   "selection. Enable it in Stellarium: Configuration > Plugins > Remote Control.")
        st_host = st.text_input("Stellarium Host",
                                value=_get("stellarium", "host", "localhost"),
                                help="Hostname where Stellarium is running. Use 'localhost' "
                                     "if it's on the same machine, or an IP address for "
                                     "a remote instance.")
        st_port = st.number_input("Stellarium Port",
                                  value=_get("stellarium", "port", 8091),
                                  min_value=1, max_value=65535,
                                  help="Stellarium Remote Control plugin port. Default is "
                                       "8091. Must match the port in Stellarium's plugin settings.")

        st.subheader("Imaging Defaults")
        st.caption("Default values used when the Imaging page loads for the first time. "
                   "These can be changed per-session on the Imaging page.")
        default_gain = st.number_input("Default Gain",
                                       value=_get("imaging", "default_gain", 80),
                                       min_value=0, max_value=400,
                                       help="Sony IMX462 sensor gain (0-400). Lower values "
                                            "= less noise but dimmer. 80 is good for deep sky, "
                                            "200+ for planets/moon.")
        default_exp = st.number_input("Default Exposure (s)",
                                      value=float(_get("imaging", "default_exposure_seconds", 10.0)),
                                      min_value=0.001, max_value=2000.0,
                                      help="Default exposure time in seconds. 10s is a good "
                                           "starting point for deep sky. Use shorter (0.01-1s) "
                                           "for planets, longer (30-120s) for faint nebulae.")
        save_dir = st.text_input("Save Directory",
                                 value=_get("imaging", "save_directory", "./captures"),
                                 help="Directory where captured images are saved. "
                                      "Relative paths are relative to the app's working "
                                      "directory. Use an absolute path for a custom location.")

        st.subheader("UI")
        refresh = st.slider("Refresh Interval (s)", 1, 10,
                            _get("ui", "refresh_interval_seconds", 2),
                            help="How often the Dashboard page auto-refreshes to show "
                                 "live telescope data. Lower = more responsive but uses "
                                 "more bandwidth. 2s is recommended.")

        if st.form_submit_button("Save Settings", type="primary"):
            _set("seestar", "ip_address", ip)
            _set("seestar", "alpaca_port", int(port))
            _set("seestar", "auto_connect", auto_connect)
            _set("stellarium", "host", st_host)
            _set("stellarium", "port", int(st_port))
            _set("imaging", "default_gain", int(default_gain))
            _set("imaging", "default_exposure_seconds", float(default_exp))
            _set("imaging", "save_directory", save_dir)
            _set("ui", "refresh_interval_seconds", refresh)

            # Write to config.toml
            config_data = config._data if hasattr(config, '_data') else config
            config_path = Path(__file__).parent.parent / "config.toml"
            try:
                with open(config_path, "w") as f:
                    toml.dump(config_data, f)
                st.success("Settings saved!")
            except Exception as e:
                st.error(f"Failed to save: {e}")

    st.divider()
    st.subheader("Connection Tests")
    st.caption("Verify connectivity to ALPACA and Stellarium before starting an imaging session.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Test ALPACA", help="Send a test request to the ALPACA server "
                     "to verify the Seestar is reachable and responding."):
            try:
                import requests
                r = requests.get(
                    f"http://{ip}:{port}/management/v1/description",
                    timeout=5,
                )
                if r.status_code == 200:
                    info = r.json().get("Value", {})
                    st.success(
                        f"Connected! Server: {info.get('ServerName')} "
                        f"v{info.get('ManufacturerVersion')}"
                    )
                else:
                    st.error(f"HTTP {r.status_code}")
            except Exception as e:
                st.error(f"Failed: {e}")
    with col2:
        if st.button("Test Stellarium", help="Check if Stellarium's Remote Control "
                     "plugin is running and accepting connections."):
            if stellarium and stellarium.is_available():
                st.success("Stellarium Remote Control is available!")
            else:
                # Fallback: direct HTTP test with form values
                try:
                    import requests
                    r = requests.get(
                        f"http://{st_host}:{st_port}/api/main/status",
                        timeout=5,
                    )
                    if r.status_code == 200:
                        st.success("Stellarium Remote Control is available!")
                    else:
                        st.error("Stellarium not responding")
                except Exception:
                    st.error("Stellarium not responding")

    st.divider()
    st.subheader("ALPACA Device Info")
    st.caption("Query each ALPACA device for its name, description, and driver version.")
    if st.button("Fetch Device Info", help="Reads identification info from all 5 "
                 "configured devices: telescope, camera, focuser, filter wheel, and switch."):
        import requests
        base = f"http://{ip}:{port}/api/v1"
        devices = ["telescope", "camera", "focuser", "filterwheel", "switch"]
        for device in devices:
            try:
                name_resp = requests.get(f"{base}/{device}/0/name", timeout=5)
                desc_resp = requests.get(f"{base}/{device}/0/description", timeout=5)
                drv_resp = requests.get(f"{base}/{device}/0/driverversion", timeout=5)
                name = name_resp.json().get("Value", "N/A") if name_resp.status_code == 200 else "N/A"
                desc = desc_resp.json().get("Value", "N/A") if desc_resp.status_code == 200 else "N/A"
                drv = drv_resp.json().get("Value", "N/A") if drv_resp.status_code == 200 else "N/A"
                st.text(f"{device.title():15s}  {name}  |  {desc}  |  Driver: {drv}")
            except requests.exceptions.RequestException:
                st.text(f"{device.title():15s}  (not reachable)")
