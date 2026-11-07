# LLDP-SyncD
SONiC Switch State Service sync daemon for LLDP data. 

See the [SONiC Website](https://sonic-net.github.io/SONiC/) for more information about the SONiC project.

## Bazel on AMD64

The Bazel path targets native Debian Trixie AMD64 with Python 3.13. It builds
the existing `sonic-d` 2.0.0 distribution and an installed runtime TAR for
`docker-lldp`. It does not produce Debian packages. The existing Make/setuptools
path remains available.

Local builds and CI use the maintained SONiC registry `main` and Bazel Central
Registry, as declared in each workspace's `.bazelrc`. The published
`tar.bzl@0.10.5.sonic.1` preserves timestamps, and
`rules_distroless@0.9.4.sonic.15` supplies the public C++ imports compatible with
Bazel 8.5.1. No temporary catalog or registry flags are needed.

```sh
bazel build //:sonic_dbsyncd_wheel //:sonic_dbsyncd_runtime
cd tests/bazel
bazel test //:unit_tests //:installed_wheel_test
```

The source libraries live beside their code in `src/sonic_syncd/BUILD.bazel`
and `src/lldp_syncd/BUILD.bazel`. Add new Python modules to those packages;
the maintained package globs include them. Update `setup.py` and the explicit
wheel definition together when adding another package, dependency or data file.
CI compares wheel payload and metadata with the original distribution and runs
the complete original suite with its existing mocks.

Consumers can depend on `@sonic_dbsyncd//:lldp_syncd` or install
`@sonic_dbsyncd//:sonic_dbsyncd_runtime` directly as an OCI layer. The wheel
contains only this repository's files. Common owns the reusable native binding;
the consuming application supplies that binding and `sonic-py-common`. The
module command remains `python3 -m lldp_syncd`.

The upstream wheel builder marks ZIP entries executable. The runtime TAR uses
upstream BSD tar and `rules_pkg` to preserve the legacy non-executable Python
files (0644), directories (0755), root ownership and zero timestamps. It retains
the installed wheel's bytes and metadata. Image consumers use the runtime TAR
to preserve that permission contract.

The test-only application under `tests/bazel` declares those external owners
and the existing config-engine requirements lock. The installed-wheel test
removes owner source paths, checks the TAR against the exact wheel, imports its
modules, checks entrypoint dispatch and writes to a private Redis process through
the real Common binding. Only the entrypoint dispatch check mocks the daemon
loop; Docker integration must additionally exercise the real `lldpd` commands
and long-running daemon. Declared external/native test dependencies are borrowed
from Bazel runfiles, so this check does not establish independent installation
of the entire dependency closure.

The standard `rules_python` wheel rule supports the distribution's runtime
metadata, author, classifiers, license and extras. It has no `Maintainer` or
`Maintainer-email` attributes. The unchanged `setup.py` retains those two legacy
contact fields; the wheel receipt records this metadata difference explicitly.

CI retains wheel/TAR hashes, resolved module graphs, generated module lockfiles,
source test inventory and installed-wheel receipts. Generated `MODULE.bazel.lock`
files are CI evidence, not manually maintained inputs.
