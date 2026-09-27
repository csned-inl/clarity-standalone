#!/usr/bin/env python3
"""Regression tests for safe use of the bundled nuXmv distribution."""

import os
import tempfile
import unittest
from pathlib import Path

from formal import _prepare_nuxmv


class NuXmvRuntimeTests(unittest.TestCase):
    def test_bundle_uses_dependencies_but_not_glibc(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "usr" / "local" / "bin" / "nuXmv"
            libraries = root / "usr" / "local" / "lib" / "x86_64-linux-gnu"
            runtime = root / "runtime"
            binary.parent.mkdir(parents=True)
            libraries.mkdir(parents=True)
            binary.touch()
            for name in ("libxml2.so.2", "libicuuc.so.70", "libc.so.6", "libm.so.6"):
                (libraries / name).touch()

            executable, environment, linked = _prepare_nuxmv(binary, runtime)

            self.assertEqual(executable, binary.resolve())
            self.assertEqual(linked, ["libicuuc.so.70", "libxml2.so.2"])
            self.assertTrue((runtime / "libxml2.so.2").is_symlink())
            self.assertFalse((runtime / "libc.so.6").exists())
            self.assertFalse((runtime / "libm.so.6").exists())
            self.assertEqual(environment["LD_LIBRARY_PATH"].split(os.pathsep)[0],
                             str(runtime))

    def test_vendor_wrapper_resolves_to_sibling_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            bin_dir = Path(temporary) / "usr" / "local" / "bin"
            bin_dir.mkdir(parents=True)
            wrapper = bin_dir / "nuXmv.sh"
            binary = bin_dir / "nuXmv"
            wrapper.touch()
            binary.touch()

            executable, _, linked = _prepare_nuxmv(
                wrapper, Path(temporary) / "runtime")

            self.assertEqual(executable, binary.resolve())
            self.assertEqual(linked, [])


if __name__ == "__main__":
    unittest.main()
