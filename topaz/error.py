import os
import errno


class RubyError(Exception):
    def __init__(self, w_value):
        self.w_value = w_value

    def __str__(self):
        return "<RubyError: %s>" % self.w_value


def format_traceback(space, exc, top_filepath):
    w_bt = space.send(exc, "backtrace")
    bt_w = space.listview(w_bt)
    if bt_w:
        yield "%s: %s (%s)\n" % (
            space.str_w(bt_w[0]), exc.msg, space.getclass(exc).name)
        for w_line in bt_w[1:]:
            yield "\tfrom %s\n" % space.str_w(w_line)
    else:
        yield "%s: %s (%s)\n" % (
            top_filepath, exc.msg, space.getclass(exc).name)


def print_traceback(space, w_exc, top_filepath=None):
    for line in format_traceback(space, w_exc, top_filepath):
        os.write(2, line)


# The platform's errnos (at translation time), canonical names first and
# then aliases such as EWOULDBLOCK; lib-topaz/errno.rb makes Errno classes
# of them.
ERRNO_LIST = []
for _code, _name in sorted(errno.errorcode.items()):
    ERRNO_LIST.append((_name, _code))
for _name in sorted(dir(errno)):
    if _name.startswith("E") and _name != errno.errorcode.get(getattr(errno, _name)):
        ERRNO_LIST.append((_name, getattr(errno, _name)))
del _code, _name

_errno_for_oserror_map = dict(errno.errorcode)


def error_for_oserror(space, exc):
    return error_for_errno(space, exc.errno)


def error_for_errno(space, errno):
    try:
        name = _errno_for_oserror_map[errno]
    except KeyError:
        return space.error(
            space.w_SystemCallError,
            os.strerror(errno),
            [space.newint(errno)]
        )
    from topaz.objects.exceptionobject import W_ExceptionObject
    w_type = space.find_const(space.find_const(space.w_object, "Errno"), name)
    # Errno classes take their message from their errno.
    w_exc = space.send(w_type, "new", [])
    assert isinstance(w_exc, W_ExceptionObject)
    return RubyError(w_exc)
