"""Exercise installed DBSyncd with its native Common binding and private Redis."""

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

import redis
from swsscommon import swsscommon
import lldp_syncd
from lldp_syncd.daemon import LldpSyncDaemon, SONIC_ETHERNET_RE_PATTERN


def main():
    site, fixture = map(Path, sys.argv[1:3])
    assert Path(lldp_syncd.__file__).resolve().is_relative_to(site.resolve())
    runtime = Path(os.environ["SWSS_RUNTIME_ROOT"]).resolve()
    executable = runtime / "usr/bin/redis-server"
    assert executable.is_file() and executable.resolve().is_relative_to(runtime)
    with tempfile.TemporaryDirectory(dir=os.environ["TEST_TMPDIR"]) as temporary:
        work = Path(temporary)
        # Native SonicV2Connector defaults to TCP. Reserve a fresh loopback
        # endpoint; never use an agent's configured Redis instance.
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        config = work / "database_config.json"
        config.write_text(json.dumps({
            "INSTANCES": {"redis": {"hostname": "127.0.0.1", "port": port,
                                    "unix_socket_path": str(work / "redis.sock")}},
            "DATABASES": {"APPL_DB": {"id": 0, "separator": ":", "instance": "redis"}},
            "VERSION": "1.0",
        }))
        with (work / "redis.log").open("w+") as log:
            process = subprocess.Popen([str(executable), "--bind", "127.0.0.1", "--port", str(port),
                                        "--save", "", "--appendonly", "no", "--dir", str(work)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                client = redis.Redis(host="127.0.0.1", port=port, db=0, decode_responses=True,
                                     socket_timeout=1, socket_connect_timeout=1)
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, "private Redis exited"
                    try:
                        if client.ping():
                            break
                    except redis.ConnectionError:
                        # A new private Redis process may not listen yet; retry
                        # until it answers or the bounded startup deadline expires.
                        pass
                    assert time.monotonic() < deadline, "private Redis did not become ready"
                    time.sleep(0.05)
                assert client.dbsize() == 0
                assert client.info("server")["process_id"] == process.pid, "Redis endpoint belongs to another process"
                swsscommon.SonicDBConfig.load_sonic_db_config(str(config))
                daemon = LldpSyncDaemon()
                assert isinstance(daemon.db_connector, swsscommon.SonicV2Connector)
                parsed = daemon.parse_update(json.loads(fixture.read_text()))
                expected = copy.deepcopy(parsed)
                chassis = expected.pop("local-chassis")
                expected = {key: value for key, value in expected.items()
                            if re.match(SONIC_ETHERNET_RE_PATTERN, key)}
                assert expected and chassis
                daemon.sync(parsed)
                for name, fields in expected.items():
                    assert client.hgetall("LLDP_ENTRY_TABLE:" + name) == {k: str(v) for k, v in fields.items()}
                assert client.hgetall("LLDP_LOC_CHASSIS") == {k: str(v) for k, v in chassis.items()}
                name = next(iter(expected))
                changed = copy.deepcopy(expected)
                changed[name]["lldp_rem_port_desc"] = "installed native binding update"
                changed["local-chassis"] = chassis
                daemon.sync(changed)
                assert client.hget("LLDP_ENTRY_TABLE:" + name, "lldp_rem_port_desc") == "installed native binding update"
                daemon.sync({"local-chassis": chassis})
                assert client.keys("LLDP_ENTRY_TABLE:*") == []
                assert client.hgetall("LLDP_LOC_CHASSIS") == {k: str(v) for k, v in chassis.items()}
                print(json.dumps({"native_binding": True, "private_redis": True,
                                  "redis_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                                  "initial_neighbors": len(expected), "neighbor_update": True,
                                  "neighbor_delete": True, "local_chassis_preserved": True,
                                  "lldpctl_input": "declared original JSON fixture; daemon process is tested by Docker integration"}))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
