import pytest

from tests.base import BaseTopazTest


class TestAncestorEntries(BaseTopazTest):
    def test_mutations_preserve_entries_and_distinguish_occurrences(self, space):
        w_class = space.execute('''
          module EntryMixin; end
          class EntryBase; include EntryMixin; end
          class EntryChild < EntryBase; end
          return EntryChild
        ''')
        before = w_class.ancestor_entries()
        assert [entry.w_module for entry in before] == w_class.ancestors()
        space.execute('EntryChild.prepend(EntryMixin)')
        after = w_class.ancestor_entries()
        assert after[1:] == before
        assert after[0].w_module is before[2].w_module
        assert after[0] is not before[2]
        space.execute('''
          module EntryAfter; end
          EntryMixin.include(EntryAfter)
        ''')
        final = w_class.ancestor_entries()
        assert [entry.w_module for entry in final] == w_class.ancestors()
        assert [entry for entry in final if entry in after] == after
        assert final[1].w_module is final[5].w_module
        assert final[1] is not final[5]

    @pytest.mark.parametrize('operation', ['dup', 'clone'])
    def test_copy_gets_independent_entries(self, space, operation):
        w_original = space.execute('''
          module EntryMixin; end
          module EntryCopy; include EntryMixin; end
          return EntryCopy
        ''')
        w_copy = space.send(w_original, operation)
        original = w_original.ancestor_entries()
        copied = w_copy.ancestor_entries()
        assert copied[0].w_module is w_copy
        assert copied[1].w_module is original[1].w_module
        assert copied[1] is not original[1]
