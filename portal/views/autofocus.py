"""Auto-Focus View — V-Curve Autofocus Control

Streamlit interface for V-curve autofocus with HFR metric.
Calls FastAPI backend at BACKEND_URL/api/autofocus/*.
"""
import os
import streamlit as st
import requests
import logging
from typing import Optional, Dict, Any
import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# Backend API base URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def render_autofocus(alpaca):
    """Main autofocus view rendering function.
    
    Args:
        alpaca: AlpacaClient instance (for context, not used directly)
    """
    st.title("🎯 Auto-Focus (V-Curve)")
    st.markdown("Automated focusing using Half-Flux Radius (HFR) metric")
    
    # Check backend connectivity
    if not check_backend_health():
        st.error(f"⚠️ Backend API is not reachable at {BACKEND_URL}. Start the FastAPI backend first.")
        st.code("cd backend && uvicorn main:app --host 0.0.0.0 --port 8503", language="bash")
        return
    
    # Get current autofocus status
    status = get_autofocus_status()
    
    if status is None:
        st.error("Failed to get autofocus status from backend")
        return
    
    is_running = status.get('running', False)
    latest_result = status.get('latest_result')
    
    # Running indicator at top
    if is_running:
        st.info("🔄 **Autofocus routine is running...** Please wait.")
    
    st.divider()
    
    # Configuration panel
    render_config_panel(is_running)
    
    st.divider()
    
    # Control buttons
    render_control_buttons(is_running)
    
    st.divider()
    
    # Results display
    if latest_result:
        render_results(latest_result)
    else:
        st.info("No autofocus results yet. Configure and start a routine above.")


def check_backend_health() -> bool:
    """Check if FastAPI backend is reachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def get_autofocus_status() -> Optional[Dict[str, Any]]:
    """Get current autofocus status from backend."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/autofocus/status", timeout=5)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Failed to get autofocus status: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error getting autofocus status: {e}")
        return None


def get_default_config() -> Optional[Dict[str, Any]]:
    """Get default autofocus configuration from backend."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/autofocus/config", timeout=5)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Failed to get default config: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error getting default config: {e}")
        return None


def render_config_panel(is_running: bool):
    """Render configuration panel with all autofocus parameters."""
    with st.expander("⚙️ Configuration", expanded=not is_running):
        st.markdown("**V-Curve Sweep Parameters**")
        
        # Get default config if not in session state
        if 'autofocus_config' not in st.session_state:
            default_config = get_default_config()
            if default_config:
                st.session_state.autofocus_config = default_config
            else:
                # Fallback defaults
                st.session_state.autofocus_config = {
                    'exposure_time': 2.0,
                    'gain': 100,
                    'step_size': 200,
                    'num_steps': 11,
                    'detection_threshold': 3.0,
                    'min_stars': 5,
                    'max_stars': 50
                }
        
        config = st.session_state.autofocus_config
        
        col1, col2 = st.columns(2)
        
        with col1:
            exposure = st.number_input(
                "Exposure Time (s)",
                min_value=0.1,
                max_value=10.0,
                value=float(config.get('exposure_time', 2.0)),
                step=0.5,
                help="Exposure duration per focus position",
                disabled=is_running
            )
            
            gain = st.number_input(
                "Gain",
                min_value=0,
                max_value=400,
                value=int(config.get('gain', 100)),
                step=10,
                help="Sensor gain (higher = more sensitive)",
                disabled=is_running
            )
            
            step_size = st.number_input(
                "Step Size",
                min_value=50,
                max_value=500,
                value=int(config.get('step_size', 200)),
                step=50,
                help="Focuser steps between measurements",
                disabled=is_running
            )
            
            num_steps = st.number_input(
                "Number of Steps",
                min_value=5,
                max_value=21,
                value=int(config.get('num_steps', 11)),
                step=2,
                help="Total positions to measure (should be odd)",
                disabled=is_running
            )
        
        with col2:
            threshold = st.number_input(
                "Detection Threshold (σ)",
                min_value=1.0,
                max_value=10.0,
                value=float(config.get('detection_threshold', 3.0)),
                step=0.5,
                help="Sigma above background for star detection",
                disabled=is_running
            )
            
            min_stars = st.number_input(
                "Min Stars Required",
                min_value=3,
                max_value=20,
                value=int(config.get('min_stars', 5)),
                step=1,
                help="Minimum stars needed for valid HFR",
                disabled=is_running
            )
            
            max_stars = st.number_input(
                "Max Stars to Measure",
                min_value=10,
                max_value=200,
                value=int(config.get('max_stars', 50)),
                step=10,
                help="Maximum stars to measure (brightest)",
                disabled=is_running
            )
        
        st.session_state.autofocus_config = {
            'exposure_time': exposure,
            'gain': gain,
            'step_size': step_size,
            'num_steps': num_steps,
            'detection_threshold': threshold,
            'min_stars': min_stars,
            'max_stars': max_stars
        }
        
        # Show sweep range estimate
        total_range = step_size * (num_steps - 1)
        st.caption(f"**Sweep range:** ±{total_range // 2} steps from current position ({total_range} total)")
        st.caption(f"**Estimated duration:** ~{num_steps * (exposure + 2)} seconds")


def render_control_buttons(is_running: bool):
    """Render Start/Abort control buttons."""
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("▶️ Start Autofocus", disabled=is_running, use_container_width=True, type="primary"):
            config = st.session_state.autofocus_config
            start_autofocus(config)

    with col2:
        if st.button("⏹️ Abort", disabled=not is_running, use_container_width=True):
            abort_autofocus()
    
    with col3:
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()


def start_autofocus(config: Dict[str, Any]):
    """Start autofocus routine with given configuration."""
    try:
        with st.spinner("Starting autofocus routine..."):
            response = requests.post(
                f"{BACKEND_URL}/api/autofocus/start",
                json=config,
                timeout=10
            )
            
            if response.status_code == 200:
                st.success("✅ Autofocus routine started!")
                st.rerun()
            elif response.status_code == 409:
                st.warning("Autofocus is already running")
            else:
                st.error(f"Failed to start autofocus: {response.status_code} - {response.text}")
    
    except Exception as e:
        logger.error(f"Error starting autofocus: {e}")
        st.error(f"Error starting autofocus: {e}")


def abort_autofocus():
    """Abort running autofocus routine."""
    try:
        with st.spinner("Aborting autofocus..."):
            response = requests.post(
                f"{BACKEND_URL}/api/autofocus/abort",
                timeout=5
            )
            
            if response.status_code == 200:
                st.success("✅ Abort signal sent")
                st.rerun()
            elif response.status_code == 404:
                st.warning("No autofocus routine running")
            else:
                st.error(f"Failed to abort: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error aborting autofocus: {e}")
        st.error(f"Error aborting autofocus: {e}")


def render_results(result: Dict[str, Any]):
    """Render autofocus results display."""
    success = result.get('success', False)
    
    if success:
        st.success("✅ **Autofocus Complete**")
    else:
        st.error("❌ **Autofocus Failed**")
        error_msg = result.get('error_message')
        if error_msg:
            st.error(f"Error: {error_msg}")
        return
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        optimal = result.get('optimal_position')
        if optimal:
            st.metric("Optimal Position", f"{optimal}")
    
    with col2:
        initial = result.get('initial_position')
        if initial:
            st.metric("Initial Position", f"{initial}")
    
    with col3:
        duration = result.get('duration_seconds')
        if duration:
            st.metric("Duration", f"{duration:.1f}s")
    
    with col4:
        v_curve_fit = result.get('v_curve_fit')
        if v_curve_fit:
            r_squared = v_curve_fit.get('r_squared', 0)
            st.metric("R² Fit Quality", f"{r_squared:.3f}")
    
    st.divider()
    
    # Measurements table and V-curve chart
    measurements = result.get('measurements', [])
    
    if measurements:
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("### 📊 Measurements")
            render_measurements_table(measurements)
        
        with col_right:
            st.markdown("### 📈 V-Curve")
            render_v_curve_chart(measurements, result.get('optimal_position'))
    
    # V-curve fit parameters
    if v_curve_fit:
        with st.expander("🔬 V-Curve Fit Parameters"):
            st.json(v_curve_fit)


def render_measurements_table(measurements: list):
    """Render measurements as a table."""
    if not measurements:
        st.info("No measurements available")
        return
    
    # Convert to DataFrame
    data = []
    for m in measurements:
        data.append({
            'Position': m.get('position'),
            'HFR': f"{m.get('hfr', 0):.2f}",
            'Stars': m.get('num_stars'),
            'Time': m.get('timestamp', '')[:19] if m.get('timestamp') else ''
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_v_curve_chart(measurements: list, optimal_position: Optional[int]):
    """Render V-curve chart (HFR vs Position)."""
    if not measurements:
        st.info("No measurements to plot")
        return
    
    # Extract data
    positions = [m.get('position') for m in measurements]
    hfrs = [m.get('hfr') for m in measurements]
    
    # Create figure
    fig = go.Figure()
    
    # Add measurement points
    fig.add_trace(go.Scatter(
        x=positions,
        y=hfrs,
        mode='markers+lines',
        name='HFR Measurements',
        marker=dict(size=10, color='#00e5ff'),
        line=dict(color='#00aaff', width=2)
    ))
    
    # Add optimal position marker
    if optimal_position:
        # Find HFR at optimal position (interpolate if not exact)
        optimal_hfr = None
        for m in measurements:
            if m.get('position') == optimal_position:
                optimal_hfr = m.get('hfr')
                break
        
        if optimal_hfr:
            fig.add_trace(go.Scatter(
                x=[optimal_position],
                y=[optimal_hfr],
                mode='markers',
                name='Optimal Focus',
                marker=dict(size=15, color='#00ff88', symbol='star')
            ))
    
    # Layout
    fig.update_layout(
        xaxis_title="Focuser Position",
        yaxis_title="HFR (pixels)",
        template="plotly_dark",
        height=400,
        showlegend=True,
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)
