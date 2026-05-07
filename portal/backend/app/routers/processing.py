"""
Processing Router for Seestar FastAPI Backend

Exposes Siril processing pipeline via REST API.
Handles image stacking, registration, and enhancement for multi-frame sequences.

AUTO-TRIGGER INTEGRATION:
    When a Streamlit capture sequence completes, call auto_trigger_processing()
    to queue Siril stacking. This function can be imported from Streamlit:
    
        from backend.app.routers.processing import auto_trigger_processing
        
        # After sequence complete
        auto_trigger_processing(
            session_id="M42_20260302_001",
            fits_files=[Path("/data/seestar/captures/M42_001.fits"), ...],
            target_name="M42",
            metadata={"exposure": 10.0, "gain": 80}
        )
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from pathlib import Path
import asyncio
import json
from datetime import datetime
import httpx

from app.services.siril_service import SirilService, ProcessingStatus, ProcessingResult

router = APIRouter(prefix="/api/processing", tags=["processing"])

# Initialize Siril service
# Output goes to gallery directory for Lal's gallery to index
siril_service = SirilService(
    data_root="/data/seestar",
    gallery_dir="/data/seestar/gallery"  # Stacked outputs here for gallery
)


# --- Request/Response Models ---

class ProcessSessionRequest(BaseModel):
    """Request to process a session of FITS files"""
    session_id: str = Field(..., description="Unique session identifier")
    fits_files: List[str] = Field(..., description="List of FITS file paths")
    target_name: str = Field(default="target", description="Target object name")
    metadata: Optional[Dict] = Field(default=None, description="Optional metadata (exposure, gain, etc.)")


class ProcessSessionResponse(BaseModel):
    """Response from processing session"""
    success: bool
    status: str
    session_id: str
    output_fits: Optional[str] = None
    output_jpeg: Optional[str] = None
    error_message: Optional[str] = None
    stats: Optional[Dict] = None


class ProcessingStatusResponse(BaseModel):
    """Status of a processing session"""
    session_id: str
    status: str
    progress: Optional[float] = None
    output_files: Optional[List[str]] = None
    error_message: Optional[str] = None


# --- Background Task Store ---
# In production, use Redis or database for task tracking
processing_tasks: Dict[str, ProcessingResult] = {}


# --- API Endpoints ---

@router.post("/sessions", response_model=ProcessSessionResponse)
async def process_session(
    request: ProcessSessionRequest,
    background_tasks: BackgroundTasks
):
    """
    Start Siril processing for a session of FITS files.
    
    Processing happens in background. Use GET /sessions/{session_id}/status
    to poll for completion, or GET /sessions/{session_id}/stream for SSE updates.
    
    **Workflow:**
    1. Convert FITS → Siril format
    2. Debayer color images (Bayer RGGB)
    3. Register frames (star alignment)
    4. Stack with sigma-clipping rejection
    5. AutoStretch for visibility
    6. Export JPEG + preserve FITS to gallery directory
    
    **Example:**
    ```json
    {
      "session_id": "M42_20260302_001",
      "fits_files": ["/data/seestar/captures/M42_frame1.fits", ...],
      "target_name": "M42",
      "metadata": {"exposure": 10.0, "gain": 80, "filter": "LP"}
    }
    ```
    """
    try:
        # Validate FITS files exist
        fits_paths = [Path(f) for f in request.fits_files]
        missing = [str(f) for f in fits_paths if not f.exists()]
        
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"FITS files not found: {missing}"
            )
        
        # Check for duplicate session
        if request.session_id in processing_tasks:
            existing = processing_tasks[request.session_id]
            if existing.status in [ProcessingStatus.PENDING, ProcessingStatus.CONVERTING,
                                   ProcessingStatus.REGISTERING, ProcessingStatus.STACKING]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Session {request.session_id} is already processing"
                )
        
        # Start processing in background
        background_tasks.add_task(
            _process_session_task,
            session_id=request.session_id,
            fits_files=fits_paths,
            target_name=request.target_name,
            metadata=request.metadata
        )
        
        # Return immediate response
        return ProcessSessionResponse(
            success=True,
            status="queued",
            session_id=request.session_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/status", response_model=ProcessingStatusResponse)
async def get_session_status(session_id: str):
    """
    Get processing status for a session.
    
    **Status values:**
    - `queued` - Waiting to start
    - `converting` - Converting FITS files
    - `registering` - Aligning frames
    - `stacking` - Combining frames
    - `stretching` - Applying histogram stretch
    - `exporting` - Creating output files
    - `complete` - Processing finished successfully
    - `failed` - Processing failed (see error_message)
    - `not_found` - Session does not exist
    """
    # Check in-memory task store
    if session_id in processing_tasks:
        result = processing_tasks[session_id]
        return ProcessingStatusResponse(
            session_id=session_id,
            status=result.status.value,
            output_files=[
                str(result.output_path) if result.output_path else None,
                str(result.jpeg_path) if result.jpeg_path else None
            ],
            error_message=result.error_message
        )
    
    # Check on disk (for completed sessions)
    status = siril_service.get_processing_status(session_id)
    return ProcessingStatusResponse(
        session_id=session_id,
        status=status.get("status", "not_found"),
        output_files=status.get("output_files")
    )


@router.get("/sessions/{session_id}/stream")
async def stream_session_status(session_id: str):
    """
    Server-Sent Events (SSE) stream for real-time processing updates.
    
    Client example (JavaScript):
    ```javascript
    const eventSource = new EventSource('/api/processing/sessions/M42_001/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(`Status: ${data.status}`);
        if (data.status === 'complete' || data.status === 'failed') {
            eventSource.close();
        }
    };
    ```
    
    Client example (Python):
    ```python
    import requests
    
    with requests.get(url, stream=True) as r:
        for line in r.iter_lines():
            if line.startswith(b'data:'):
                data = json.loads(line[5:])
                print(f"Status: {data['status']}")
    ```
    """
    async def event_generator():
        """Generate SSE events for processing status"""
        while True:
            # Check task status
            if session_id in processing_tasks:
                result = processing_tasks[session_id]
                event_data = {
                    "session_id": session_id,
                    "status": result.status.value,
                    "timestamp": datetime.now().isoformat()
                }
                
                if result.status == ProcessingStatus.COMPLETE:
                    event_data["output_fits"] = str(result.output_path) if result.output_path else None
                    event_data["output_jpeg"] = str(result.jpeg_path) if result.jpeg_path else None
                    event_data["stats"] = result.stats
                    
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break  # Complete, stop streaming
                
                elif result.status == ProcessingStatus.FAILED:
                    event_data["error"] = result.error_message
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break  # Failed, stop streaming
                
                else:
                    # Still processing
                    yield f"data: {json.dumps(event_data)}\n\n"
            else:
                # Not found yet, wait
                yield f"data: {json.dumps({'status': 'waiting', 'session_id': session_id})}\n\n"
            
            await asyncio.sleep(2)  # Poll every 2 seconds

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.delete("/sessions/{session_id}")
async def cancel_session(session_id: str):
    """
    Cancel a processing session (if still running).
    
    Note: Siril subprocess cannot be cleanly interrupted mid-processing.
    This will mark the session as cancelled, but Siril may continue until
    the current step completes.
    """
    if session_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Session not found")
    
    result = processing_tasks[session_id]
    
    if result.status in [ProcessingStatus.COMPLETE, ProcessingStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Session already {result.status.value}"
        )
    
    # Mark as failed (cancellation)
    processing_tasks[session_id] = ProcessingResult(
        success=False,
        status=ProcessingStatus.FAILED,
        error_message="Cancelled by user"
    )
    
    return {"message": f"Session {session_id} cancelled"}


# --- AUTO-TRIGGER HELPER (for Streamlit integration) ---

def auto_trigger_processing(
    session_id: str,
    fits_files: List[Path],
    target_name: str,
    metadata: Optional[Dict] = None,
    backend_url: str = "http://localhost:8503"
) -> Dict:
    """
    Auto-trigger Siril processing after a capture sequence completes.
    
    This function should be called from Streamlit when a sequence finishes
    capturing all frames. It queues the Siril stacking job via the FastAPI backend.
    
    **Integration Example (in views/sequence.py):**
    ```python
    from backend.app.routers.processing import auto_trigger_processing
    
    # After sequence complete (around line 235)
    if idx >= len(targets):
        st.session_state.sequence_running = False
        
        # AUTO-TRIGGER PROCESSING
        if st.session_state.get("auto_process", True):  # Opt-out checkbox
            result = auto_trigger_processing(
                session_id=f"{target['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                fits_files=[Path(f) for f in captured_fits_files],
                target_name=target["name"],
                metadata={"exposure": target["exposure"], "gain": target["gain"]}
            )
            if result["success"]:
                st.success(f"Processing queued: {result['session_id']}")
        
        st.success("Sequence complete!")
        st.balloons()
        return
    ```
    
    Args:
        session_id: Unique session identifier
        fits_files: List of captured FITS file paths
        target_name: Target object name
        metadata: Optional metadata (exposure, gain, filter, etc.)
        backend_url: FastAPI backend URL (default: localhost:8503)
        
    Returns:
        Dict with 'success', 'session_id', 'status' keys
    """
    try:
        payload = {
            "session_id": session_id,
            "fits_files": [str(f) for f in fits_files],
            "target_name": target_name,
            "metadata": metadata or {}
        }
        
        response = httpx.post(
            f"{backend_url}/api/processing/sessions",
            json=payload,
            timeout=10.0
        )
        
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# --- Background Task ---

async def _process_session_task(
    session_id: str,
    fits_files: List[Path],
    target_name: str,
    metadata: Optional[Dict]
):
    """
    Background task for Siril processing.
    Updates processing_tasks dict with status.
    """
    # Mark as pending
    processing_tasks[session_id] = ProcessingResult(
        success=False,
        status=ProcessingStatus.PENDING
    )
    
    # Execute Siril processing (blocking, but in background thread)
    # Use asyncio.to_thread to avoid blocking event loop
    result = await asyncio.to_thread(
        siril_service.process_session,
        session_id=session_id,
        fits_files=fits_files,
        target_name=target_name,
        metadata=metadata
    )
    
    # Update task store with final result
    processing_tasks[session_id] = result


# --- Health Check ---

@router.get("/health")
async def health_check():
    """
    Check if Siril CLI is available and processing service is healthy.
    """
    try:
        import subprocess
        result = subprocess.run(
            [siril_service.siril_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            return {
                "status": "healthy",
                "siril_version": result.stdout.strip(),
                "data_root": str(siril_service.data_root),
                "gallery_dir": str(siril_service.gallery_dir)
            }
        else:
            return {
                "status": "degraded",
                "error": "Siril CLI not responding correctly"
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
