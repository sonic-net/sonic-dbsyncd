"""Validate the owner wheel away from its checkout and original test mocks."""

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import unittest
import zipfile

from tools.bazel.tests.integration.installed_wheel_fixture import installed_wheels, write_wheel_receipt
from tools.bazel.tests.integration.wheel_contract import setup_contract


parser = argparse.ArgumentParser()
for name in ("wheel", "runtime-tar", "setup", "common-wheel", "redis-probe"):
    parser.add_argument("--" + name, type=Path, required=True)
INPUTS, REST = parser.parse_known_args()
DETAILS = {}


class InstalledWheelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wheels = [INPUTS.common_wheel.absolute(), INPUTS.wheel.absolute()]
        cls.setup = INPUTS.setup.absolute()
        import sonic_py_common
        cls.installed = cls.enterClassContext(installed_wheels(
            cls.wheels, exclude_source_roots=[cls.setup.parent,
                Path(sonic_py_common.__file__).absolute().parent.parent]))
        cls.contract = setup_contract(cls.setup)

    def test_complete_owner_payload_and_metadata(self):
        root = self.setup.parent / "src"
        expected = {str(path.relative_to(root)): path
                    for name in self.contract["packages"]
                    for path in (root / name.replace(".", "/")).glob("*.py")}
        self.assertEqual(set(self.contract["packages"]), {"lldp_syncd", "sonic_syncd"})
        with zipfile.ZipFile(INPUTS.wheel) as archive:
            actual = {name for name in archive.namelist() if name.endswith(".py")}
            self.assertEqual(actual, set(expected))
            for name, path in expected.items():
                self.assertEqual(archive.read(name), path.read_bytes(), name)
                self.assertEqual((self.installed.site / name).read_bytes(), path.read_bytes(), name)
            metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            self.assertEqual(len(metadata_names), 1)
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
            for key, setup_key in (("Name", "name"), ("Version", "version"), ("License", "license"),
                                   ("Author", "author"), ("Author-email", "author_email")):
                self.assertEqual(metadata[key], self.contract[setup_key], key)
            self.assertEqual(metadata.get_all("Requires-Dist", []), self.contract["install_requires"])
            self.assertEqual(set(metadata.get_all("Classifier", [])), set(self.contract["classifiers"]))
            self.assertEqual(set(metadata.get_all("Provides-Extra", [])), set(self.contract["extras_require"]))
            license_names = [name for name in archive.namelist() if name.endswith("/licenses/LICENSE")]
            self.assertEqual(len(license_names), 1)
            self.assertEqual(archive.read(license_names[0]), (self.setup.parent / "LICENSE").read_bytes())
            # rules_python's public py_wheel has no Maintainer attributes.
            # Keep the legacy setup.py intact and report this metadata gap.
            for key in ("Maintainer", "Maintainer-email"):
                self.assertIsNone(metadata[key])
        DETAILS["owner_python_files"] = len(expected)
        DETAILS["metadata_difference"] = {
            "Maintainer": self.contract["maintainer"],
            "Maintainer-email": self.contract["maintainer_email"],
            "reason": "Not supported by rules_python py_wheel; legacy setup.py retains these fields",
        }
        DETAILS["dependency_boundary"] = "Exact owner and sonic-py-common wheels installed; declared external/native dependencies borrowed from runfiles"

    def test_runtime_tar_installs_the_same_owner_wheel(self):
        prefix = "usr/local/lib/python3.13/dist-packages/"
        with zipfile.ZipFile(INPUTS.wheel) as wheel, tarfile.open(INPUTS.runtime_tar) as layer:
            members = {str(Path(member.name)): member for member in layer.getmembers() if member.isfile()}
            own_modules = {name for name in members if name.endswith(".py")}
            expected_modules = {prefix + name for name in wheel.namelist() if name.endswith(".py")}
            self.assertEqual(own_modules, expected_modules)
            for name in wheel.namelist():
                if name.endswith("/") or name.endswith(".dist-info/RECORD"):
                    continue
                member = members[prefix + name]
                self.assertEqual((member.uid, member.gid, member.mode, member.mtime),
                                 (0, 0, 0o644, 0), name)
                self.assertEqual(layer.extractfile(member).read(), wheel.read(name), name)
            for member in layer.getmembers():
                if member.isdir():
                    self.assertEqual((member.uid, member.gid, member.mode, member.mtime),
                                     (0, 0, 0o755, 0), member.name)
        DETAILS["runtime_tar_wheel_bytes_match"] = True
        DETAILS["runtime_tar_file_mode"] = "0644 (legacy source mode; upstream wheel ZIP entries use 0777)"
        DETAILS["runtime_tar_sha256"] = hashlib.sha256(INPUTS.runtime_tar.read_bytes()).hexdigest()

    def test_installed_imports_and_module_entry_dispatch(self):
        # This is an entrypoint dispatch check. The separate native Redis probe
        # covers writes; Docker LLDP integration covers the real lldpctl process.
        probe = r'''
import importlib, importlib.metadata, json, pathlib, runpy, sys
from unittest.mock import patch
site = pathlib.Path(sys.argv[1]).resolve()
modules = ('lldp_syncd', 'lldp_syncd.daemon', 'lldp_syncd.main', 'lldp_syncd.conventions',
           'sonic_syncd', 'sonic_syncd.interface', 'sonic_py_common.util')
for name in modules:
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(site), (name, module.__file__)
distribution = importlib.metadata.distribution('sonic-d')
assert distribution.version == '2.0.0'
assert pathlib.Path(distribution.locate_file('')).resolve() == site
sys.argv = ['lldp_syncd', '-d', '10']
with patch('lldp_syncd.main.main') as main:
    runpy.run_module('lldp_syncd', run_name='__main__')
    main.assert_called_once_with(update_frequency=None)
print(json.dumps({'installed_modules': list(modules), 'module_entry_dispatch': True,
                  'daemon_loop_mocked_only_for_entry_dispatch': True}))
'''
        result = subprocess.run([str(self.installed.python), "-I", "-c", probe, str(self.installed.site)],
                                cwd=self.installed.root, env=self.installed.env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        DETAILS.update(json.loads(result.stdout))

    def test_native_redis_sync_without_owner_source_or_original_mocks(self):
        result = subprocess.run([
            str(self.installed.python), "-I", str(INPUTS.redis_probe.absolute()),
            str(self.installed.site), str(self.setup.parent / "tests/subproc_outputs/lldpctl.json"),
        ], cwd=self.installed.root, env=self.installed.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        DETAILS.update(json.loads(result.stdout))


if __name__ == "__main__":
    result = unittest.main(argv=[__file__, *REST], exit=False).result
    write_wheel_receipt(getattr(InstalledWheelTest, "wheels", None), required=True,
                        status="passed" if result.wasSuccessful() else "failed",
                        details=dict(DETAILS, tests_run=result.testsRun))
    raise SystemExit(not result.wasSuccessful())
