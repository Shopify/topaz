import os

import pytest

from topaz import main


class FakeSpace(object):
    def setup(self, executable):
        pass


def prepare(monkeypatch, tmpdir):
    path = str(tmpdir.join("topaz.prof"))
    events = []
    fds = []

    def enable(fd, interval):
        assert interval == 0.001
        fds.append(fd)
        events.append("enable")
        os.write(fd, "header")

    def disable():
        events.append("disable")
        os.write(fds[0], "trailer")

    monkeypatch.setenv("TOPAZ_VMPROF", path)
    monkeypatch.setattr(main, "we_are_translated", lambda: True)
    monkeypatch.setattr(main, "VMPROF_SUPPORTED", True)
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

    def fail(fd, interval):
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


@pytest.mark.parametrize("translated, supported", [(False, True), (True, False)])
def test_unavailable(monkeypatch, tmpdir, capfd, translated, supported):
    path, events, fds = prepare(monkeypatch, tmpdir)
    monkeypatch.setattr(main, "we_are_translated", lambda: translated)
    monkeypatch.setattr(main, "VMPROF_SUPPORTED", supported)
    assert main._run_with_vmprof(FakeSpace(), ["topaz"]) == 1
    assert not events
    assert not os.path.exists(path)
    assert "requires a translated build" in capfd.readouterr()[1]
