import os
import sys
# noinspection PyUnresolvedReferences
import tests.mock_tables.dbconnector


modules_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(modules_path, 'src'))

from unittest import TestCase
import json
import re
import lldp_syncd
import lldp_syncd.conventions
import lldp_syncd.daemon
from swsssdk import SonicV2Connector

INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subproc_outputs')


def create_dbconnector():
    db = SonicV2Connector()
    db.connect(db.APPL_DB)
    return db


def make_seconds(days, hours, minutes, seconds):
    """
    >>> make_seconds(0,5,9,5)
    18545
    """
    return seconds + (60 * minutes) + (60 * 60 * hours) + (24 * 60 * 60 * days)


class TestLldpSyncDaemon(TestCase):
    def setUp(self):
        with open(os.path.join(INPUT_DIR, 'lldpctl.json')) as f:
            self._json = json.load(f)

        with open(os.path.join(INPUT_DIR, 'lldpctl_mgmt_only.json')) as f:
            self._json_short = json.load(f)

        with open(os.path.join(INPUT_DIR, 'short_short.json')) as f:
            self._json_short_short = json.load(f)

        self.daemon = lldp_syncd.LldpSyncDaemon()

    def test_parse_json(self):
        jo = self.daemon.parse_update(self._json)
        print(json.dumps(jo, indent=3))

    def test_parse_short(self):
        jo = self.daemon.parse_update(self._json_short)
        print(json.dumps(jo, indent=3))

    def test_parse_short_short(self):
        jo = self.daemon.parse_update(self._json_short_short)
        print(json.dumps(jo, indent=3))

    def test_sync_roundtrip(self):
        parsed_update = self.daemon.parse_update(self._json)
        self.daemon.sync(parsed_update)
        db = create_dbconnector()
        keys = db.keys(db.APPL_DB)

        dump = {}
        for k in keys:
            dump[k] = db.get_all(db.APPL_DB, k)
        print(json.dumps(dump, indent=3))

        # convert dict keys to ints for easy comparison
        jo = {int(re.findall(r'\d+', k)[0]): v for k, v in parsed_update.items()}
        r_out = {int(re.findall(r'\d+', k)[0]): v for k, v in dump.items()}
        self.assertEqual(jo, r_out)

        # test enumerations
        for k, v in r_out.items():
            chassis_subtype = v['lldp_rem_chassis_id_subtype']
            chassis_id = v['lldp_rem_chassis_id']
            if int(chassis_subtype) == lldp_syncd.conventions.LldpChassisIdSubtype.macAddress:
                if re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', chassis_id) is None:
                    self.fail("Non-mac returned for chassis ID")
            else:
                self.fail("Test data only contains chassis MACs")

    def test_timeparse(self):
        self.assertEquals(lldp_syncd.daemon.parse_time("0 day, 05:09:02"), make_seconds(0, 5, 9, 2))
        self.assertEquals(lldp_syncd.daemon.parse_time("2 days, 05:59:02"), make_seconds(2, 5, 59, 2))
