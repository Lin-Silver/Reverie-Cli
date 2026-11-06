"""Run Harness²'s local workflow with Windows locks and normalized tree paths.

This provides only the LOCK_EX/LOCK_UN calls used by the pinned scheduler.
It does not make the Linux benchmark executors available on Windows.
"""
import argparse
import os
from pathlib import Path
import runpy
import sys
import types


def install_summary_lock():
    if sys.platform != 'win32':
        return
    import msvcrt
    module = types.ModuleType('fcntl')
    module.LOCK_EX, module.LOCK_UN = 2, 8

    def flock(file, operation):
        if operation not in (module.LOCK_EX, module.LOCK_UN):
            raise ValueError('The Harness² Windows adapter supports only exclusive summary locks')
        descriptor = file if isinstance(file, int) else file.fileno()
        offset = os.lseek(descriptor, 0, os.SEEK_CUR)
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            # Python documents LK_LOCK's bounded retries and locking beyond EOF:
            # https://docs.python.org/3.12/library/msvcrt.html#msvcrt.locking
            msvcrt.locking(descriptor, msvcrt.LK_LOCK if operation == module.LOCK_EX else msvcrt.LK_UNLCK, 1)
        finally:
            os.lseek(descriptor, offset, os.SEEK_SET)

    module.flock = flock
    sys.modules['fcntl'] = module


def install_tree_paths():
    """Keep editable tree keys in the upstream POSIX form on Windows."""
    if sys.platform != 'win32':
        return
    from harness2.core import tree
    original = tree.read_tree
    if getattr(original, 'windows_paths', False):
        return

    def read_tree(surface, directory, *, rejected=None):
        rejected_paths = []
        value = original(surface, directory, rejected=rejected_paths)
        stubs = {path for path, _ in surface.stubs}
        if rejected is not None:
            rejected.extend(tree.normalize_rel(path) for path in rejected_paths if tree.normalize_rel(path) not in stubs)
        return {tree.normalize_rel(key): content for key, content in value.items()}

    read_tree.windows_paths = True
    tree.read_tree = read_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    install_summary_lock()
    install_tree_paths()
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    sys.argv = ['harness2-demo', *arguments]
    runpy.run_module('harness2.cli.demo', run_name='__main__')


if __name__ == '__main__':
    main()
