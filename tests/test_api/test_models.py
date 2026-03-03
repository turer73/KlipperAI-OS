"""Tests for Pydantic data models."""


def test_print_status_model():
    from packages.api.models.printer import PrintStatus

    status = PrintStatus(
        state="printing",
        filename="test.gcode",
        progress=0.45,
        print_duration=1800,
        total_duration=3600,
        filament_used=123.4,
        current_layer=45,
        total_layers=100,
    )
    assert status.state == "printing"
    assert status.progress == 0.45


def test_temperature_model():
    from packages.api.models.printer import TemperatureReading

    temps = TemperatureReading(
        extruder_current=210.0,
        extruder_target=210.0,
        bed_current=60.0,
        bed_target=60.0,
    )
    assert temps.extruder_current == 210.0


def test_print_status_from_moonraker():
    from packages.api.models.printer import PrintStatus

    raw = {
        "print_stats": {
            "state": "printing",
            "filename": "test.gcode",
            "total_duration": 3600,
            "print_duration": 1800,
            "filament_used": 100.0,
            "info": {"current_layer": 10, "total_layer": 50},
        },
        "display_status": {"progress": 0.2},
    }
    status = PrintStatus.from_moonraker(raw)
    assert status.state == "printing"
    assert status.progress == 0.2
    assert status.current_layer == 10
    assert status.total_layers == 50
