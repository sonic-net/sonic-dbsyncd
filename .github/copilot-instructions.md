# Copilot Instructions for sonic-dbsyncd

## Project Overview

sonic-dbsyncd provides Python-based database synchronization daemons for SONiC. The primary component is LLDP-SyncD, which syncs LLDP (Link Layer Discovery Protocol) data from the lldpd daemon into the SONiC Redis database. The repo also provides a generic `sonic_syncd` interface for building additional database sync daemons that bridge external data sources into SONiC's centralized Redis state.

## Architecture

```
sonic-dbsyncd/
├── src/                          # Source code root
│   ├── __init__.py
│   ├── lldp_syncd/               # LLDP database sync daemon
│   │   ├── __init__.py
│   │   ├── __main__.py           # Entry point for lldp_syncd
│   │   ├── daemon.py             # Main daemon loop
│   │   ├── main.py               # Startup logic
│   │   └── conventions.py        # LLDP data formatting conventions
│   └── sonic_syncd/              # Generic sync daemon interface
│       ├── __init__.py
│       └── interface.py          # Base interface for sync daemons
├── tests/                        # Unit/integration tests
├── setup.py                      # Python package setup
├── README.md
└── .github/                      # CI workflows
```

### Key Concepts
- **SyncD pattern**: A daemon that subscribes to an external data source and writes structured data into SONiC's Redis database
- **LLDP-SyncD**: Reads LLDP neighbor information from `lldpd` (via lldpctl) and populates `APPL_DB` LLDP tables
- **Generic interface**: `sonic_syncd.interface` provides a base class that new sync daemons can implement
- **Redis DB integration**: Uses `swsscommon` Python bindings to write to SONiC databases

## Language & Style

- **Primary language**: Python 3
- **Style**: PEP 8 compliant
- **Indentation**: 4 spaces
- **Naming conventions**:
  - Classes: `PascalCase` (e.g., `LldpSyncDaemon`)
  - Functions/methods: `snake_case` (e.g., `sync_data`)
  - Constants: `UPPER_SNAKE_CASE`
  - Modules: `snake_case`
- **Docstrings**: Use Python docstrings for public classes and methods
- **Imports**: Standard library first, then third-party, then local

## Build Instructions

```bash
# Install Python dependencies
pip3 install -e .

# Or build Debian package
dpkg-buildpackage -us -uc -b

# The package installs:
#   - lldp_syncd module
#   - sonic_syncd module
```

## Testing

```bash
# Run tests
cd tests
python3 -m pytest -v

# Or run individual test files
python3 -m pytest tests/test_lldp_syncd.py -v
```

### Test Structure
- Tests are in the `tests/` directory
- Use `pytest` framework
- May require mock `swsscommon` module for unit testing without Redis

## PR Guidelines

- **Signed-off-by**: REQUIRED on all commits (`git commit -s`)
- **CLA**: Sign the Linux Foundation EasyCLA
- **Single commit per PR**: Squash commits before merge
- **PEP 8**: Code must pass linting (flake8 or similar)
- **Tests**: Add or update tests for any behavioral changes
- **Reference issues**: Link related GitHub issues in PR description

## Dependencies

- **sonic-swss-common**: Python bindings (`swsscommon`) for Redis DB access
- **lldpd**: External LLDP daemon whose data is consumed by lldp_syncd
- **sonic-py-swsssdk**: SONiC Python SDK for database connectivity
- **Redis**: Backend database for SONiC operational state

## Gotchas

- **lldpctl dependency**: LLDP-SyncD relies on `lldpctl` (lldpd CLI tool) being installed and accessible
- **swsscommon import**: The `swsscommon` Python module is built from `sonic-swss-common` and must be installed in the Python path
- **Daemon lifecycle**: The sync daemon runs as a systemd service; handle signals (SIGTERM) gracefully
- **Data format**: LLDP data formatting in `conventions.py` must match what consumers (SNMP, CLI) expect
- **Testing without hardware**: Unit tests must mock external dependencies (lldpctl, swsscommon)
- **Python version**: Targets Python 3; do not use Python 2 constructs
- **Entry points**: `lldp_syncd` is run as a module (`python3 -m lldp_syncd`)
- **DB schema changes**: Any change to Redis table schema must be coordinated with consumers (e.g., `sonic-snmpagent`, `sonic-utilities`)
