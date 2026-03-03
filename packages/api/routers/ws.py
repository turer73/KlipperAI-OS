"""WebSocket gercek zamanli yazici stream."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..dependencies import get_moonraker_client

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/printer")
async def ws_printer_stream(ws: WebSocket) -> None:
    await ws.accept()
    mr = get_moonraker_client()
    try:
        while True:
            data = mr.get_printer_objects(
                "print_stats", "extruder", "heater_bed", "display_status",
            )
            await ws.send_json({
                "type": "printer_update",
                "data": data,
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
