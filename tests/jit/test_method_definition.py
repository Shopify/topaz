import os
import re
import subprocess

import pytest


@pytest.mark.parametrize("source", ["", "def f; end"])
def test_instance_eval_does_not_abort_quasi_immutable(topaz, tmpdir, source):
    script = tmpdir.join("definitions.rb")
    script.write('10000.times { Object.new.instance_eval("%s") }' % source)
    log = tmpdir.join("jit.log")
    env = os.environ.copy()
    env["PYPYLOG"] = "jit-invalidate-quasi-immutable,jit-summary:%s" % log
    subprocess.check_call([str(topaz), str(script)], env=env)
    summary = log.read()
    match = re.search(r"abort: force quasi-immut:\s+(\d+)", summary)
    assert match is not None
    assert int(match.group(1)) == 0, summary
