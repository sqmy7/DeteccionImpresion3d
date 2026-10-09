import pytest

from capture.camera_sources.device_names import CameraNotFound, resolve_usb_target


def devices(*names):
    return lambda: list(names)


def test_an_index_or_a_path_is_used_as_it_always_was():
    never = devices()  # must not be asked
    index = resolve_usb_target("0", never)
    assert (index.value, index.directshow) == (0, False)
    path = resolve_usb_target("/dev/video2", never)
    assert (path.value, path.directshow) == ("/dev/video2", False)


def test_a_named_camera_is_found_by_part_of_its_name_whatever_its_index():
    # What happened on 2026-10-08: a generic webcam took index 0 and the Logitech was no longer the first.
    target = resolve_usb_target("name:c922", devices("USB Camera", "C922 Pro Stream Webcam"))
    assert (target.value, target.directshow) == (1, True)
    assert "C922 Pro Stream Webcam" in target.description and "index 1" in target.description
    # and with the Logitech alone it is index 0, so the same setting works in both situations
    assert resolve_usb_target("name:C922", devices("C922 Pro Stream Webcam")).value == 0


def test_a_missing_camera_is_an_error_that_lists_what_is_connected_never_another_camera():
    with pytest.raises(CameraNotFound) as error:
        resolve_usb_target("name:C922", devices("USB Camera", "Integrated Camera"))
    assert "'C922'" in str(error.value) and "'USB Camera'" in str(error.value) and "'Integrated Camera'" in str(error.value)
    with pytest.raises(CameraNotFound, match="none"):
        resolve_usb_target("name:C922", devices())


def test_more_than_one_match_uses_the_first_and_an_empty_name_is_refused(caplog):
    target = resolve_usb_target("name:USB", devices("Integrated Camera", "USB Camera", "USB 2.0 Web Camera"))
    assert target.value == 1
    assert "More than one camera" in caplog.text
    with pytest.raises(CameraNotFound, match="names no camera"):
        resolve_usb_target("name:", devices("USB Camera"))


def test_without_the_listing_library_a_named_camera_says_what_is_missing(monkeypatch):
    def unavailable():
        raise CameraNotFound("Selecting a camera by name needs pygrabber (pip install pygrabber)")

    with pytest.raises(CameraNotFound, match="pygrabber"):
        resolve_usb_target("name:C922", unavailable)
