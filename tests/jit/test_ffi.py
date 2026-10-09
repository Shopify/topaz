from .base import BaseJITTest


class TestFFI(BaseJITTest):
    def test_constant_signature(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        require 'ffi'
        module Native
          extend FFI::Library
          ffi_lib FFI::Library::LIBC
          attach_function :abs, [:int], :int
        end
        def ffi_loop
          i = 0
          total = 0
          while i < 10000
            total += Native.abs(-i)
            i += 1
          end
          total
        end
        raise 'wrong result' unless ffi_loop == 49995000
        ''')
        loop = self.ruby_loop(traces, 'ffi_loop')
        assert len([op for op in loop
                    if op.name == 'call_release_gil_i']) == 1
        # The complete signature, including conversion strategies and sizes,
        # is constant. No type metadata should be read in the steady loop.
        for op in loop:
            descr = str(op.descr)
            assert 'W_TypeObject' not in descr
            assert 'RWStrategy' not in descr
