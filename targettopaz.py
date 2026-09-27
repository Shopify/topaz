import os

from rpython.jit.codewriter.policy import JitPolicy

from topaz.main import create_entry_point, get_topaz_config_options


BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")


def target(driver, args):
    driver.exe_name = "topaz"
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
