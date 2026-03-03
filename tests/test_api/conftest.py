import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_moonraker_response():
    """Ornek Moonraker yaniti."""
    return {
        "result": {
            "status": {
                "print_stats": {"state": "printing", "filename": "test.gcode"},
                "extruder": {"temperature": 210.0, "target": 210.0, "power": 0.8},
                "heater_bed": {"temperature": 60.0, "target": 60.0, "power": 0.5},
                "display_status": {"progress": 0.45},
            }
        }
    }
