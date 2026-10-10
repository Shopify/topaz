"""Untranslated bytecode inspection; never invokes Ruby inspect methods."""
import sys

from topaz import consts
from topaz.objects.codeobject import W_CodeObject


JUMPS = ('JUMP', 'JUMP_IF_TRUE', 'JUMP_IF_FALSE',
         'JUMP_IF_KWARG_GIVEN', 'CONTINUE_LOOP')
CONSTANT_OPS = (
    'LOAD_CONST', 'LOAD_CONSTANT', 'STORE_CONSTANT', 'DEFINED_CONSTANT',
    'LOAD_LOCAL_CONSTANT', 'DEFINED_LOCAL_CONSTANT',
    'LOAD_INSTANCE_VAR', 'STORE_INSTANCE_VAR', 'DEFINED_INSTANCE_VAR',
    'LOAD_CLASS_VAR', 'STORE_CLASS_VAR', 'DEFINED_CLASS_VAR',
    'LOAD_GLOBAL', 'STORE_GLOBAL', 'DEFINED_GLOBAL',
    'SEND', 'SEND_BLOCK', 'SEND_SPLAT', 'SEND_BLOCK_SPLAT',
    'SEND_SUPER_BLOCK', 'SEND_SUPER_BLOCK_SPLAT',
    'DEFINED_METHOD', 'DEFINED_SUPER')


def constant_repr(value):
    from topaz.objects.bignumobject import W_BignumObject
    from topaz.objects.boolobject import W_TrueObject, W_FalseObject
    from topaz.objects.floatobject import W_FloatObject
    from topaz.objects.intobject import W_FixnumObject
    from topaz.objects.nilobject import W_NilObject
    from topaz.objects.stringobject import W_StringObject, inspect_string
    from topaz.objects.symbolobject import W_SymbolObject, symbol_needs_quotes

    if isinstance(value, W_CodeObject):
        return '<code %s, file %r, line %d>' % (
            value.name, value.filepath, value.lineno)
    if isinstance(value, W_SymbolObject):
        if symbol_needs_quotes(value.symbol):
            return ':' + inspect_string(value.symbol)
        return ':' + value.symbol
    if isinstance(value, W_StringObject):
        return inspect_string(value.str_w(None))
    if isinstance(value, W_FixnumObject):
        return str(value.intvalue)
    if isinstance(value, W_BignumObject):
        return value.bigint.str()
    if isinstance(value, W_FloatObject):
        return repr(value.floatvalue)
    if isinstance(value, W_NilObject):
        return 'nil'
    if isinstance(value, W_TrueObject):
        return 'true'
    if isinstance(value, W_FalseObject):
        return 'false'
    return '<%s>' % type(value).__name__


def instructions(code):
    pc = 0
    while pc < len(code.code):
        start = pc
        opcode = ord(code.code[pc])
        pc += 1
        args = []
        for _ in range(consts.BYTECODE_NUM_ARGS[opcode]):
            args.append(ord(code.code[pc]) | ord(code.code[pc + 1]) << 8)
            pc += 2
        yield start, pc, consts.BYTECODE_NAMES[opcode], args


def annotation(code, name, args):
    if name in CONSTANT_OPS:
        return constant_repr(code.consts_w[args[0]])
    if name in ('LOAD_DEREF', 'STORE_DEREF', 'LOAD_CLOSURE'):
        return (code.cellvars + code.freevars)[args[0]]
    if name in JUMPS:
        result = 'to %d' % args[0]
        if name == 'JUMP_IF_KWARG_GIVEN':
            result += ', keyword %s' % code.kwarg_names[args[1]]
        return result
    if name == 'END_FINALLY':
        return 'resume handler %d' % (args[0] - 1)
    if name == 'CLEAR_STACK':
        return 'depth %d' % args[0]
    return ''


def disassemble(code, file=None, depth=None):
    if file is None:
        file = sys.stdout
    instrs = list(instructions(code))
    targets = set(args[0] for _, _, name, args in instrs if name in JUMPS)
    targets.update(handler.target_pc for handler in code.unwind_handlers)
    targets.update(code.default_entry_pcs)
    previous_line = None
    for pc, end, name, args in instrs:
        lineno = code.lineno_table[pc]
        line = ''
        if lineno != previous_line:
            if previous_line is not None:
                file.write('\n')
            line = str(lineno) if lineno >= 0 else ''
            previous_line = lineno
        text = '%3s %2s %4d %-24s' % (
            line, '>>' if pc in targets else '', pc, name)
        if args:
            text += ' %s' % ', '.join(str(arg) for arg in args)
            note = annotation(code, name, args)
            if note:
                text += ' (%s)' % note
        file.write(text.rstrip() + '\n')
    if code.unwind_intervals:
        # CPython displays inclusive instruction offsets, not the exclusive
        # byte boundary stored in the table. Instructions here vary in size.
        last_offsets = dict((end, pc) for pc, end, _, _ in instrs)
        file.write('ExceptionTable:\n')
        for interval in code.unwind_intervals:
            handler = code.unwind_handlers[interval.handler]
            file.write('  %d to %d -> %d [%d] %s handler=%d parent=%d\n' % (
                interval.start, last_offsets[interval.end], handler.target_pc,
                handler.stackdepth, ('loop', 'rescue', 'ensure')[handler.kind],
                interval.handler, handler.parent))
        # A parent can be reachable only via another handler, without having
        # an interval of its own. Preserve the entire chain for inspection.
        file.write('Handlers:\n')
        for idx, handler in enumerate(code.unwind_handlers):
            file.write('  %d: %s -> %d [%d] parent=%d\n' % (
                idx, ('loop', 'rescue', 'ensure')[handler.kind],
                handler.target_pc, handler.stackdepth, handler.parent))
    if depth is None or depth > 0:
        for value in code.consts_w:
            if isinstance(value, W_CodeObject):
                file.write('\nDisassembly of %s:\n' % constant_repr(value))
                disassemble(value, file, None if depth is None else depth - 1)
