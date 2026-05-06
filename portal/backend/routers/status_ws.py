"""WebSocket Live Status Router for Seestar Backend

Provides real-time bidirectional status updates via WebSocket.
Broadcasts telescope position, tracking state, and processing job status to all connected clients.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from typing import Dict, Set
import asyncio
import json
import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

router = APIRouter()


class MessageType(str, Enum):
    """WebSocket message types"""
    TELESCOPE_STATUS = "telescope_status"
    PROCESSING_STATUS = "processing_status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    CONNECTED = "connected"


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
        await self.send_personal_message({
            "type": MessageType.CONNECTED,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected to Seestar status stream"
        }, websocket)

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
            telescope_status = alpaca.get_telescope_status()
            camera_status = alpaca.get_camera_status()
            focuser_status = alpaca.get_focuser_status()
            message = {
                "type": MessageType.TELESCOPE_STATUS,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "telescope": {
                        "connected": telescope_status.get("connected", False),
                        "tracking": telescope_status.get("tracking", False),
                        "slewing": telescope_status.get("slewing", False),
                        "ra": telescope_status.get("ra"),
                        "dec": telescope_status.get("dec"),
                        "altitude": telescope_status.get("altitude"),
                        "azimuth": telescope_status.get("azimuth"),
                        "at_park": telescope_status.get("at_park", False)
                    },
                    "camera": {
                        "state": camera_status.get("state", "unknown"),
                        "temperature": camera_status.get("temperature"),
                        "cooler_on": camera_status.get("cooler_on", False),
                        "gain": camera_status.get("gain")
                    },
                    "focuser": {
                        "position": focuser_status.get("position"),
                        "is_moving": focuser_status.get("is_moving", False),
                        "temperature": focuser_status.get("temperature")
                    }
                }
            }
            await manager.broadcast(message)
        except Exception as e:
            logger.error(f"Telescope status broadcast error: {e}")
            await manager.broadcast({
                "type": MessageType.ERROR,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            })
        await asyncio.sleep(2.0)


async def processing_status_broadcaster(request: Request) -> None:
    """Background task: broadcast processing job status updates"""
    from backend.routers.processing import processing_tasks
    last_states: Dict[str, str] = {}
    while True:
        try:
            for session_id, result in processing_tasks.items():
                current_state = result.status.value
                if last_states.get(session_id) != current_state:
                    message = {
                        "type": MessageType.PROCESSING_STATUS,
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {
                            "session_id": session_id,
                            "status": current_state,
                            "output_fits": str(result.output_path) if result.output_path else None,
                            "output_jpeg": str(result.jpeg_path) if result.jpeg_path else None,
                            "error_message": result.error_message,
                            "stats": result.stats
                        }
                    }
                    await manager.broadcast(message)
                    last_states[session_id] = current_state
        except Exception as e:
            logger.error(f"Processing status broadcast error: {e}")
        await asyncio.sleep(1.0)


async def heartbeat_sender() -> None:
    """Background task: send periodic heartbeat to detect dead connections"""
    while True:
        await asyncio.sleep(30.0)
        try:
            await manager.broadcast({
                "type": MessageType.HEARTBEAT,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, request: Request):
    """WebSocket endpoint for real-time status updates.

    Connection URL: ws://localhost:8503/api/status/ws

    Message types: telescope_status (2s), processing_status (on change),
    heartbeat (30s), error, connected.
    """
    await manager.connect(websocket)

    # Start background tasks if not already running
    if not hasattr(request.app.state, "_ws_tasks_started"):
        request.app.state._ws_tasks_started = True
        asyncio.create_task(telescope_status_broadcaster(request))
        asyncio.create_task(processing_status_broadcaster(request))
        asyncio.create_task(heartbeat_sender())
        logger.info("WebSocket background tasks started")

    sender_task = asyncio.create_task(manager.client_sender(websocket))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("command") == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }, websocket)
                elif message.get("command") == "subscribe":
                    await manager.send_personal_message({
                        "type": "subscribed",
                        "channels": message.get("channels", ["all"])
                    }, websocket)
                else:
                    await manager.send_personal_message({
                        "type": MessageType.ERROR,
                        "error": f"Unknown command: {message.get('command')}"
                    }, websocket)
            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": MessageType.ERROR,
                    "error": "Invalid JSON"
                }, websocket)
    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        sender_task.cancel()
        await manager.disconnect(websocket)


@router.get("/connections")
async def get_active_connections():
    """Get count of active WebSocket connections."""
    return {
        "active_connections": len(manager.active_connections),
        "timestamp": datetime.utcnow().isoformat()
    }
