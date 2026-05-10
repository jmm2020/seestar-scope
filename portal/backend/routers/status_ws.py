"""WebSocket Live Status Router for Seestar Backend

Provides real-time bidirectional status updates via WebSocket.
Broadcasts telescope position, tracking state, and processing job status to all connected clients.
Replaces SSE for modern real-time communication with heartbeat and reconnect support.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from typing import Dict, Set
import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["status"])


class MessageType(str, Enum):
    """WebSocket message types"""

    TELESCOPE_STATUS = "telescope_status"
    PROCESSING_STATUS = "processing_status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    CONNECTED = "connected"
    STACK_PROGRESS = "stack_progress"


class ConnectionManager:
    """Manages WebSocket connections with fan-out broadcasting"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.client_queues: Dict[WebSocket, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            self.client_queues[websocket] = asyncio.Queue()

        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

        # Send welcome message
        await self.send_personal_message(
            {
                "type": MessageType.CONNECTED,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Connected to Seestar status stream",
            },
            websocket,
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection"""
        async with self._lock:
            self.active_connections.discard(websocket)
            self.client_queues.pop(websocket, None)

        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        # Add message to all client queues
        async with self._lock:
            for queue in self.client_queues.values():
                try:
                    await queue.put(message)
                except Exception as e:
                    logger.error(f"Failed to queue message: {e}")

    async def client_sender(self, websocket: WebSocket) -> None:
        """Send messages from client queue to WebSocket"""
        queue = self.client_queues.get(websocket)
        if not queue:
            return

        try:
            while websocket in self.active_connections:
                message = await queue.get()
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Client sender error: {e}")
        finally:
            await self.disconnect(websocket)


# Global connection manager
manager = ConnectionManager()


async def telescope_status_broadcaster(request: Request) -> None:
    """Background task: poll telescope status and broadcast to all clients"""
    alpaca = request.app.state.alpaca

    while True:
        try:
            # Poll telescope status
            telescope_status = alpaca.get_telescope_status()
            camera_status = alpaca.get_camera_status()
            focuser_status = alpaca.get_focuser_status()

            # Build status message
            message = {
                "type": MessageType.TELESCOPE_STATUS,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "telescope": {
                        "connected": telescope_status.get("connected", False),
                        "tracking": telescope_status.get("tracking", False),
                        "slewing": telescope_status.get("slewing", False),
                        "ra": telescope_status.get("ra"),
                        "dec": telescope_status.get("dec"),
                        "altitude": telescope_status.get("altitude"),
                        "azimuth": telescope_status.get("azimuth"),
                        "at_park": telescope_status.get("at_park", False),
                    },
                    "camera": {
                        "state": camera_status.get("state", "unknown"),
                        "temperature": camera_status.get("temperature"),
                        "cooler_on": camera_status.get("cooler_on", False),
                        "gain": camera_status.get("gain"),
                    },
                    "focuser": {
                        "position": focuser_status.get("position"),
                        "is_moving": focuser_status.get("is_moving", False),
                        "temperature": focuser_status.get("temperature"),
                    },
                },
            }

            # Broadcast to all clients
            await manager.broadcast(message)

        except Exception as e:
            logger.error(f"Telescope status broadcast error: {e}")
            # Broadcast error to clients
            await manager.broadcast(
                {
                    "type": MessageType.ERROR,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )

        # Poll every 2 seconds
        await asyncio.sleep(2.0)


async def processing_status_broadcaster(request: Request) -> None:
    """Background task: broadcast processing job status updates"""
    # Import here to avoid circular dependency
    from backend.routers.processing import processing_tasks

    last_states: Dict[str, str] = {}

    while True:
        try:
            # Check for processing status changes
            for session_id, result in processing_tasks.items():
                current_state = result.status.value

                # Only broadcast if state changed
                if last_states.get(session_id) != current_state:
                    message = {
                        "type": MessageType.PROCESSING_STATUS,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": {
                            "session_id": session_id,
                            "status": current_state,
                            "output_fits": str(result.output_path) if result.output_path else None,
                            "output_jpeg": str(result.jpeg_path) if result.jpeg_path else None,
                            "error_message": result.error_message,
                            "stats": result.stats,
                        },
                    }

                    await manager.broadcast(message)
                    last_states[session_id] = current_state

        except Exception as e:
            logger.error(f"Processing status broadcast error: {e}")

        # Check every 1 second (faster than telescope polling)
        await asyncio.sleep(1.0)


async def heartbeat_sender() -> None:
    """Background task: send periodic heartbeat to detect dead connections"""
    while True:
        await asyncio.sleep(30.0)  # Heartbeat every 30 seconds

        try:
            await manager.broadcast(
                {"type": MessageType.HEARTBEAT, "timestamp": datetime.now(timezone.utc).isoformat()}
            )
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")


async def stack_progress_broadcaster(request: Request) -> None:
    """Background task: poll Seestar view state and broadcast stack progress."""
    alpaca = request.app.state.alpaca
    last_frame_count: int = -1
    last_is_stacking: bool = False

    while True:
        try:
            view_data = alpaca.get_view_state()
            if view_data:
                view = view_data.get("View", view_data)
                stage = view.get("stage", "")
                is_stacking = stage == "Stack"
                stack_data = view.get("Stack", {})
                try:
                    frame_count = int(float(stack_data.get("count", 0) or 0))
                except (ValueError, TypeError):
                    frame_count = last_frame_count if last_frame_count >= 0 else 0
                lapse_ms = view.get("lapse_ms", 0)

                state = {
                    "frame_count": frame_count,
                    "elapsed_s": round(lapse_ms / 1000, 1) if lapse_ms else 0,
                    "snr_estimate": round(frame_count**0.5, 2) if frame_count > 0 else 0.0,
                    "is_stacking": is_stacking,
                    "stage": stage,
                    "mode": view.get("mode", "unknown"),
                    "target": view.get("target_name", ""),
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }

                # Persist for reconnect recovery
                request.app.state.live_stack_state = state

                # Only broadcast on change to avoid noise
                if frame_count != last_frame_count or is_stacking != last_is_stacking:
                    await manager.broadcast(
                        {
                            "type": MessageType.STACK_PROGRESS,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": state,
                        }
                    )
                    last_frame_count = frame_count
                    last_is_stacking = is_stacking

        except Exception as e:
            logger.error(f"Stack progress broadcast error: {e}")
            await manager.broadcast(
                {
                    "type": MessageType.ERROR,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": f"Stack progress unavailable: {e}",
                }
            )

        await asyncio.sleep(3.0)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, request: Request):
    """
    WebSocket endpoint for real-time status updates.

    **Connection URL:** ws://<host>:8503/api/status/ws

    **Message Types:**
    - `telescope_status`: Real-time telescope position, tracking, slewing state (every 2s)
    - `processing_status`: Processing job status updates (pushed on state change)
    - `stack_progress`: Live stack frame count, elapsed time, SNR estimate (every 3s, on change only)
    - `heartbeat`: Connection health check (every 30s)
    - `error`: Error notifications
    - `connected`: Welcome message on connection

    **Client Example (JavaScript):**
    ```javascript
    const ws = new WebSocket('ws://<host>:8503/api/status/ws');

    ws.onopen = () => {
        console.log('Connected to Seestar status stream');
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        switch(msg.type) {
            case 'telescope_status':
                console.log('Telescope:', msg.data.telescope);
                updateTelescopeUI(msg.data);
                break;
            case 'processing_status':
                console.log('Processing:', msg.data.status);
                updateProcessingUI(msg.data);
                break;
            case 'stack_progress':
                console.log('Stack:', msg.data.frame_count, 'frames');
                updateStackUI(msg.data);
                break;
            case 'heartbeat':
                console.log('Heartbeat:', msg.timestamp);
                break;
            case 'error':
                console.error('Error:', msg.error);
                break;
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
        console.log('Disconnected. Reconnecting in 5s...');
        setTimeout(() => location.reload(), 5000);
    };
    ```

    **Client Example (Python):**
    ```python
    import websocket
    import json

    def on_message(ws, message):
        msg = json.loads(message)
        print(f"{msg['type']}: {msg.get('data', msg.get('message', ''))}")

    def on_error(ws, error):
        print(f"Error: {error}")

    def on_close(ws, close_status_code, close_msg):
        print("Connection closed")

    def on_open(ws):
        print("Connected to Seestar status stream")

    ws = websocket.WebSocketApp(
        "ws://<host>:8503/api/status/ws",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()
    ```

    **Reconnect Strategy:**
    Client should implement exponential backoff on disconnect:
    - First retry: 1s
    - Second retry: 2s
    - Third retry: 4s
    - Max retry: 30s
    """
    # Accept connection
    await manager.connect(websocket)

    # Send current stack state for reconnect recovery
    live_stack = getattr(request.app.state, "live_stack_state", None)
    if live_stack:
        await manager.send_personal_message(
            {
                "type": MessageType.STACK_PROGRESS,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": live_stack,
            },
            websocket,
        )

    # Start background tasks if not already running
    if not hasattr(request.app.state, "_ws_tasks_started"):
        request.app.state._ws_tasks_started = True

        # Launch broadcaster tasks
        asyncio.create_task(telescope_status_broadcaster(request))
        asyncio.create_task(processing_status_broadcaster(request))
        asyncio.create_task(heartbeat_sender())
        asyncio.create_task(stack_progress_broadcaster(request))

        logger.info("WebSocket background tasks started")

    # Start client sender task
    sender_task = asyncio.create_task(manager.client_sender(websocket))

    try:
        # Listen for client messages (bidirectional communication)
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle client commands
                if message.get("command") == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()},
                        websocket,
                    )

                elif message.get("command") == "subscribe":
                    # Future enhancement: selective subscription
                    await manager.send_personal_message(
                        {"type": "subscribed", "channels": message.get("channels", ["all"])},
                        websocket,
                    )

                else:
                    await manager.send_personal_message(
                        {
                            "type": MessageType.ERROR,
                            "error": f"Unknown command: {message.get('command')}",
                        },
                        websocket,
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": MessageType.ERROR, "error": "Invalid JSON"}, websocket
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        sender_task.cancel()
        await manager.disconnect(websocket)


@router.get("/connections")
async def get_active_connections():
    """
    Get count of active WebSocket connections.

    **Response:**
    ```json
    {
        "active_connections": 3,
        "timestamp": "2026-03-02T12:34:56.789Z"
    }
    ```
    """
    return {
        "active_connections": len(manager.active_connections),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/live-stack")
async def get_live_stack_state(request: Request):
    """Current live stack state for reconnect/refresh recovery.

    Returns the last known state from the stack_progress_broadcaster.
    Clients should fetch this on page load before the WebSocket connects.
    """
    state = getattr(request.app.state, "live_stack_state", {})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
    }
