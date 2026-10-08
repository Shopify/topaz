import os
import struct
from StringIO import StringIO

import pytest

from rpython.rlib import rvmprof
from topaz.utils import vmprof


def word(value):
    return struct.pack("l", value)


def string(value):
    return word(len(value)) + value


def profile(version=6, memory=False):
    data = struct.pack("lllll", 0, 3, 0, 1000, 0)
    data += "\x05" + struct.pack(">h", version) + chr(12 + int(memory)) + "\x04pypy"
    data += "\x06" + "\x00" * 24
    data += "\x07" + string("os") + string("linux")
    data += "\x02" + word(8) + string("rb:burn:1:test.rb")
    for address in (101, 101, 201):
        data += "\x01" + word(1) + word(4)
        data += word(1) + word(8) + word(7) + word(address)
        data += word(123)  # thread
        if memory:
            data += word(4096)
        if version == 7:
            data += struct.pack("q", 1000000)
    return data + "\x03" + "\x00" * 24


@pytest.mark.parametrize("version", [6, 7])
@pytest.mark.parametrize("memory", [False, True])
def test_native_addresses(version, memory):
    data = profile(version, memory)
    addresses, position, trailer = vmprof.native_addresses(StringIO(data))
    assert set(addresses) == set([101, 201])
    assert data[position:] == trailer == "\x03" + "\x00" * 24


def test_truncated_profile():
    with pytest.raises(rvmprof.VMProfError):
        vmprof.native_addresses(StringIO(profile()[:-1]))


def test_unknown_version():
    with pytest.raises(rvmprof.VMProfError):
        vmprof.native_addresses(StringIO(profile(8)))


def test_write_native_symbols(tmpdir, monkeypatch):
    names = {101: "n:first:12:first.c", 201: "n:second:24:second.c"}
    resolved = []

    def resolve(address):
        resolved.append(address)
        return names[address]

    monkeypatch.setattr(vmprof, "resolve_name", resolve)
    path = str(tmpdir.join("native.prof"))
    original = profile()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0600)
    try:
        os.write(fd, original)
        vmprof.write_native_symbols(fd)
        os.fstat(fd)  # the caller still owns the descriptor
    finally:
        os.close(fd)
    with open(path) as result:
        data = result.read()
    assert sorted(resolved) == [101, 201]
    assert data.startswith(original[:-25])
    assert data.endswith(original[-25:])
    for address, name in names.items():
        assert "\x08" + word(address) + string(name) in data
    # The added records do not disturb the samples or the end marker.
    assert set(vmprof.native_addresses(StringIO(data))[0]) == set(names)
