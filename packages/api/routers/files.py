"""G-code dosya yonetimi endpoint'leri."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from ..dependencies import get_moonraker_client
from ..moonraker_client import MoonrakerClient
from ..models.printer import GCodeFileInfo

router = APIRouter(prefix="/api/v1/files", tags=["files"])

@router.get("/gcodes", response_model=list[GCodeFileInfo])
async def list_gcode_files(mr: MoonrakerClient = Depends(get_moonraker_client)):
    resp = mr.get("/server/files/list?root=gcodes")
    files = []
    if resp and "result" in resp:
        for f in resp["result"]:
            files.append(GCodeFileInfo(
                filename=f.get("path", ""),
                size=f.get("size", 0),
                modified=f.get("modified", 0),
            ))
    return files
