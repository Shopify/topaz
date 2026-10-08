import os

import pytest

from topaz import main


class FakeSpace(object):
    def setup(self, executable):
        pass


def prepare(monkeypatch, tmpdir, expected_interval=0.01):
    path = str(tmpdir.join("topaz.prof"))
    events = []
    fds = []

    def enable(fd, interval, native):
        assert interval == expected_interval
        assert native == 1
        fds.append(fd)
        events.append("enable")
        os.write(fd, "header")

    def disable():
        events.append("disable")
        os.write(fds[0], "trailer")

    monkeypatch.delenv("TOPAZ_VMPROF_INTERVAL", raising=False)
    monkeypatch.setenv("TOPAZ_VMPROF", path)
    monkeypatch.setattr(main, "we_are_translated", lambda: True)
    monkeypatch.setattr(main, "VMPROF_SUPPORTED", True)
    monkeypatch.setattr(main, "NATIVE_SUPPORTED", True)
    monkeypatch.setattr(main, "write_native_symbols", lambda fd: None)
    monkeypatch.setattr(main.rvmprof, "enable", enable)
    monkeypatch.setattr(main.rvmprof, "disable", disable)
    return path, events, fds


@pytest.mark.parametrize("status", [0, 7])
def test_recording_preserves_status(monkeypatch, tmpdir, status):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def run(space, argv):
        events.append("run")
        return status

    monkeypatch.setattr(main, "_entry_point", run)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == status
    assert events == ["enable", "run", "disable"]
    with pytest.raises(OSError):
        os.fstat(fds[0])
    with open(path) as profile:
        assert profile.read() == "headertrailer"


def test_disabled(monkeypatch, tmpdir):
    path, events, fds = prepare(monkeypatch, tmpdir)
    monkeypatch.delenv("TOPAZ_VMPROF")
    monkeypatch.setattr(main, "_entry_point", lambda space, argv: 0)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 0
    assert not events
    assert not os.path.exists(path)


def test_native_unsupported(monkeypatch, tmpdir):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def enable(fd, interval, native):
        assert native == 0
        fds.append(fd)
        events.append("enable")

    def unexpected_symbols(fd):
        pytest.fail("native resolution on an unsupported platform")

    monkeypatch.setattr(main, "NATIVE_SUPPORTED", False)
    monkeypatch.setattr(main.rvmprof, "enable", enable)
    monkeypatch.setattr(main, "write_native_symbols", unexpected_symbols)
    monkeypatch.setattr(main, "_entry_point", lambda space, argv: 0)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 0
    assert events == ["enable", "disable"]


@pytest.mark.parametrize("during_setup", [False, True])
def test_cleanup_on_exception(monkeypatch, tmpdir, during_setup):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def fail(*args):
        raise ValueError("failed")

    if during_setup:
        monkeypatch.setattr(FakeSpace, "setup", fail)
    else:
        monkeypatch.setattr(main, "_entry_point", fail)
    with pytest.raises(ValueError):
        main._run_with_vmprof(FakeSpace(), ["topaz"])
    assert events == ["enable", "disable"]
    with pytest.raises(OSError):
        os.fstat(fds[0])
    with open(path) as profile:
        assert profile.read() == "headertrailer"


def test_enable_error(monkeypatch, tmpdir, capfd):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def fail(fd, interval, native):
        fds.append(fd)
        raise main.rvmprof.VMProfError("enable failed")

    monkeypatch.setattr(main.rvmprof, "enable", fail)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert not events
    assert "cannot enable vmprof: enable failed" in capfd.readouterr()[1]
    with pytest.raises(OSError):
        os.fstat(fds[0])


@pytest.mark.parametrize("status, expected", [(0, 1), (7, 7)])
def test_disable_error(monkeypatch, tmpdir, capfd, status, expected):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def fail():
        raise main.rvmprof.VMProfError("flush failed")

    monkeypatch.setattr(main.rvmprof, "disable", fail)
    monkeypatch.setattr(main, "_entry_point", lambda space, argv: status)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == expected
    assert "cannot finish vmprof profile: flush failed" in capfd.readouterr()[1]
    with pytest.raises(OSError):
        os.fstat(fds[0])


def test_open_error(monkeypatch, tmpdir, capfd):
    path, events, fds = prepare(monkeypatch, tmpdir)
    monkeypatch.setenv("TOPAZ_VMPROF", str(tmpdir.join("missing", "out.prof")))
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert not events
    assert "cannot open vmprof output" in capfd.readouterr()[1]


def test_symbol_error_closes_file(monkeypatch, tmpdir, capfd):
    path, events, fds = prepare(monkeypatch, tmpdir)

    def fail(fd):
        raise main.rvmprof.VMProfError("bad profile")

    monkeypatch.setattr(main, "write_native_symbols", fail)
    monkeypatch.setattr(main, "_entry_point", lambda space, argv: 0)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert events == ["enable", "disable"]
    assert "bad profile" in capfd.readouterr()[1]
    with pytest.raises(OSError):
        os.fstat(fds[0])


@pytest.mark.parametrize("translated, supported", [(False, True), (True, False)])
def test_unavailable(monkeypatch, tmpdir, capfd, translated, supported):
    path, events, fds = prepare(monkeypatch, tmpdir)
    monkeypatch.setattr(main, "we_are_translated", lambda: translated)
    monkeypatch.setattr(main, "VMPROF_SUPPORTED", supported)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert not events
    assert not os.path.exists(path)
    assert "requires a translated build" in capfd.readouterr()[1]


@pytest.mark.parametrize("value", ["0.1", "0.005", "0.000001", "0.999999"])
def test_custom_interval(monkeypatch, tmpdir, value):
    path, events, fds = prepare(monkeypatch, tmpdir, float(value))
    monkeypatch.setenv("TOPAZ_VMPROF_INTERVAL", value)
    monkeypatch.setattr(main, "_entry_point", lambda space, argv: 0)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 0
    assert events == ["enable", "disable"]


@pytest.mark.parametrize("value", ["", "oops", "0", "-1", "1", "0.0000001",
                                   "nan", "inf", "-inf", "1e999"])
def test_invalid_interval_preserves_output(monkeypatch, tmpdir, capfd, value):
    path, events, fds = prepare(monkeypatch, tmpdir)
    with open(path, "w") as output:
        output.write("existing profile")
    monkeypatch.setenv("TOPAZ_VMPROF_INTERVAL", value)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert "TOPAZ_VMPROF_INTERVAL must be seconds" in capfd.readouterr()[1]
    assert not events
    with open(path) as output:
        assert output.read() == "existing profile"


def test_interval_rtyping():
    from rpython.rtyper.test.test_llinterp import gengraph
    gengraph(main._get_vmprof_interval, [])
