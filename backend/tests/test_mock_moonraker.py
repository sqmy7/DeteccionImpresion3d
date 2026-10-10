import pytest


def _print_until_layer(printer, layer: int) -> None:
    for _ in range(5000):
        if printer.layer >= layer:
            return
        printer.tick(0.05)
    raise AssertionError(f"the simulated print never reached layer {layer}")


def test_console_commands_change_the_simulated_state(mock_moonraker):
    printer = mock_moonraker.printer
    printer.start(mock_moonraker.MOCK_FILE)
    _print_until_layer(printer, 1)

    printer.run_gcode("M104 S250\nM220 S80\nM221 S95\nM106 S255\nSET_GCODE_OFFSET Z_ADJUST=0.05\nEXCLUDE_OBJECT NAME=BOX_2")

    assert printer.extruder.target == 250
    assert printer.speed_factor == pytest.approx(0.8)
    assert printer.extrude_factor == pytest.approx(0.95)
    assert printer.fan_speed == 1.0
    assert printer.homing_origin[2] == pytest.approx(0.05)
    assert printer.excluded == ["BOX_2"]
    assert [entry["type"] for entry in printer.gcode_store] == ["command"] * 6 + ["response"]


def test_unknown_console_command_is_reported_like_klipper(mock_moonraker):
    printer = mock_moonraker.printer
    with pytest.raises(mock_moonraker.GcodeError):
        printer.run_gcode("FOO")
    assert list(printer.gcode_store)[-1]["message"] == '!! Unknown command:"FOO"'


def test_pause_parks_the_head_and_resume_returns_it(mock_moonraker):
    printer = mock_moonraker.printer
    printer.start(mock_moonraker.MOCK_FILE)
    _print_until_layer(printer, 1)
    printing_position = list(printer.position)

    printer.pause()
    assert printer.state == "paused"
    assert printer.position[:2] == [mock_moonraker.PARK_X, mock_moonraker.PARK_Y]

    printer.resume()
    assert printer.state == "printing"
    assert printer.position == printing_position


def test_creality_quirks_are_reproduced(mock_moonraker):
    printer = mock_moonraker.printer
    printer.start(mock_moonraker.MOCK_FILE)
    _print_until_layer(printer, 2)

    status = printer.status({"print_stats": None, "virtual_sdcard": None})

    assert status["print_stats"]["info"]["current_layer"] is None
    assert status["virtual_sdcard"]["layer"] == 2
    assert status["virtual_sdcard"]["cur_print_data"]["metadata"]["layer_height"] == 0.2
    assert status["print_stats"]["z_pos"] == 0.2  # still the first layer's height: it lags


def test_subscription_updates_carry_only_changed_fields(mock_moonraker):
    client = mock_moonraker.WsClient(ws=None)
    first = client.status_diff({"extruder": {"temperature": 200.0, "target": 240.0}})
    second = client.status_diff({"extruder": {"temperature": 201.5, "target": 240.0}})
    third = client.status_diff({"extruder": {"temperature": 201.5, "target": 240.0}})

    assert first == {"extruder": {"temperature": 200.0, "target": 240.0}}
    assert second == {"extruder": {"temperature": 201.5}}
    assert third == {}
