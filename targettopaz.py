import os

from rpython.jit.codewriter.policy import JitPolicy

from topaz.main import create_entry_point, get_topaz_config_options


BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")


def target(driver, args):
    driver.exe_name = "topaz"
    enlarge_jit_counter_table()
    driver.config.set(**get_topaz_config_options())

    # RPython copies the finished executable into the *current directory*
    # under its basename, which here would collide with the ``topaz``
    # package.  Do the copy from bin/ instead, so the result is still
    # bin/topaz.
    orig_create_exe = driver.create_exe

    def create_exe():
        cwd = os.getcwd()
        os.chdir(BIN_DIR)
        try:
            orig_create_exe()
        finally:
            os.chdir(cwd)
    driver.create_exe = create_exe

    return create_entry_point(driver.config), None


def enlarge_jit_counter_table():
    """Give the JIT a 65536-entry counter table instead of RPython's 2048.

    The table holds every function-entry counter (how many times a method
    was called from the interpreter, against function_threshold) and every
    guard-failure counter (against trace_eagerness) in a 5-way,
    16-bit-subhash cache: 2048 entries is 10240 counters. A Rails app has
    ~10k code objects and the compiled traces of lobsters hold 400k+
    guards, so counters were evicted long before reaching their
    threshold: methods called thousands of times per request stayed
    interpreted and guards failed forever without getting a bridge. On
    lobsters at 40 iterations this took interpreted bytecodes per 10
    iterations from 26M to 3M, guard-failure frames from 605k to 58k, and
    the time per iteration from ~980ms to ~840ms, at the cost of +50%
    tracing time and ~600MiB more RSS from the extra bridges. 65536 is the
    largest size JitCounter accepts (it needs 16 bits of index); the table
    itself is 2MiB. The size is not a JitDriver parameter, hence the patch
    of the constructor's default at translation time.
    """
    from rpython.jit.metainterp import counter
    orig_init = counter.JitCounter.__init__

    def __init__(self, size=65536, translator=None):
        orig_init(self, size, translator)
    counter.JitCounter.__init__ = __init__


def jitpolicy(driver):
    return JitPolicy()


def handle_config(config, translateconfig):
    from rpython.translator.platform import host_factory
    max_stack_size = 11 << 18  # 2.8 Megs
    if host_factory.name == 'msvc':
        host_factory.cflags += ('/DMAX_STACK_SIZE=%d' % max_stack_size,)
    elif host_factory.name in ('linux', 'darwin'):
        host_factory.cflags += ('-DMAX_STACK_SIZE=%d' % max_stack_size,)
    config.translation.suggest(check_str_without_nul=True)
