import errno
import os
import zlib

import pytest

from rpython.rlib import rgc
from topaz.utils import heapdump

from ..base import BaseTopazTest


class TestHeapDump(BaseTopazTest):
    def fake_metadata(self, monkeypatch):
        monkeypatch.setattr(heapdump, "we_are_translated", lambda: True)
        monkeypatch.setattr(rgc, "get_typeids_z",
                            lambda: zlib.compress("member0 ?\nmember1 TestObject\n"))
        monkeypatch.setattr(rgc, "get_typeids_list", lambda: [0, 42])

    def test_dump(self, space, tmpdir, monkeypatch):
        self.fake_metadata(monkeypatch)
        path = tmpdir.join("heap.dump")
        path.write("old contents that must be truncated")
        tmpdir.join("typeids.txt").write("stale metadata")
        descriptors = []

        def dump(fd):
            descriptors.append(fd)
            os.write(fd, "heap graph")
            return True

        monkeypatch.setattr(rgc, "dump_rpy_heap", dump)
        result = space.execute('return Topaz.dump_rpy_heap("%s")' % path)
        assert result is space.w_nil
        assert path.read() == "heap graph"
        assert tmpdir.join("typeids.txt").read() == "member0 ?\nmember1 TestObject\n"
        assert tmpdir.join("typeids.lst").read() == "0\n42\n"
        with pytest.raises(OSError):
            os.fstat(descriptors[0])

    def test_write_error(self, space, tmpdir, monkeypatch):
        self.fake_metadata(monkeypatch)
        descriptors = []

        def dump(fd):
            descriptors.append(fd)
            raise OSError(errno.ENOSPC, "disk full")

        monkeypatch.setattr(rgc, "dump_rpy_heap", dump)
        with self.raises(space, "Errno::ENOSPC"):
            space.execute('Topaz.dump_rpy_heap("%s")' % tmpdir.join("heap.dump"))
        with pytest.raises(OSError):
            os.fstat(descriptors[0])

    def test_untranslated(self, space, tmpdir):
        with self.raises(space, "NotImplementedError"):
            space.execute('Topaz.dump_rpy_heap("%s")' % tmpdir.join("heap.dump"))
        assert not tmpdir.listdir()

    def test_unsupported_gc(self, space, tmpdir, monkeypatch):
        self.fake_metadata(monkeypatch)
        descriptors = []

        def dump(fd):
            descriptors.append(fd)
            return False

        monkeypatch.setattr(rgc, "dump_rpy_heap", dump)
        with self.raises(space, "NotImplementedError"):
            space.execute('Topaz.dump_rpy_heap("%s")' % tmpdir.join("heap.dump"))
        with pytest.raises(OSError):
            os.fstat(descriptors[0])

    def test_missing_directory(self, space, tmpdir, monkeypatch):
        self.fake_metadata(monkeypatch)
        with self.raises(space, "Errno::ENOENT"):
            space.execute('Topaz.dump_rpy_heap("%s")' %
                          tmpdir.join("missing", "heap.dump"))

    def test_reserved_name(self, space, tmpdir):
        with self.raises(space, "ArgumentError"):
            space.execute('Topaz.dump_rpy_heap("%s")' % tmpdir.join("typeids.txt"))
        assert not tmpdir.listdir()

    def test_path_coercion(self, space, tmpdir, monkeypatch):
        self.fake_metadata(monkeypatch)
        monkeypatch.setattr(rgc, "dump_rpy_heap", lambda fd: True)
        result = space.execute('''
        path = Object.new
        def path.to_path
          "%s"
        end
        return Topaz.dump_rpy_heap(path)
        ''' % tmpdir.join("heap.dump"))
        assert result is space.w_nil
