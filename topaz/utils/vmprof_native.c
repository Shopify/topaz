#include "symboltable.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __linux__
#include "backtrace.h"

static struct backtrace_state *topaz_symbol_state;

struct topaz_symbol_result {
    char *name;
    int size;
};

static void topaz_symbol_error(void *data, const char *message, int error)
{
    /* Missing symbols are represented by an address in the profile. */
}

static void topaz_symbol_found(void *data, uintptr_t pc, const char *name,
                               uintptr_t value, uintptr_t size)
{
    struct topaz_symbol_result *result = (struct topaz_symbol_result *)data;
    if (name != NULL)
        snprintf(result->name, result->size, "%s", name);
}
#endif

void topaz_vmprof_resolve_addr(void *addr, char *name, int name_size,
                               int *line, char *file, int file_size)
{
    vmp_resolve_addr(addr, name, name_size, line, file, file_size);
#ifdef __linux__
    /* vmprof tries DWARF and then dladdr. Normal RPython builds have no
       DWARF, and their local pypy_g_* functions are absent from .dynsym.
       libbacktrace can also read .symtab, which retains those names. */
    if (name[0] == '\0') {
        struct topaz_symbol_result result = {name, name_size};
        if (topaz_symbol_state == NULL)
            topaz_symbol_state = backtrace_create_state(
                NULL, 0, topaz_symbol_error, NULL);
        if (topaz_symbol_state != NULL)
            backtrace_syminfo(topaz_symbol_state, (uintptr_t)addr,
                             topaz_symbol_found, topaz_symbol_error, &result);
    }
#endif
}
