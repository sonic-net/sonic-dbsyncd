import datetime
import json
import re
import subprocess
import time
from collections import defaultdict

from enum import unique, Enum
from swsssdk import SonicV2Connector

from sonic_syncd import SonicSyncDaemon
from . import logger
from .conventions import LldpPortIdSubtype, LldpChassisIdSubtype

LLDPD_TIME_FORMAT = '%H:%M:%S'

DEFAULT_UPDATE_INTERVAL = 10

SONIC_ETHERNET_RE_PATTERN = r'^(Ethernet(\d+)|eth0)$'
LLDPD_UPTIME_RE_SPLIT_PATTERN = r' days?, '
MANAGEMENT_PORT_NAME = 'eth0'


def parse_time(time_str):
    """
    From LLDPd/src/client/display.c:
    static const char*
    display_age(time_t lastchange)
    {
        static char sage[30];
        int age = (int)(time(NULL) - lastchange);
        if (snprintf(sage, sizeof(sage),
            "%d day%s, %02d:%02d:%02d",
            age / (60*60*24),
            (age / (60*60*24) > 1)?"s":"",
            (age / (60*60)) % 24,
            (age / 60) % 60,
            age % 60) >= sizeof(sage))
            return "too much";
        else
            return sage;
    }
    :return: parsed age in time ticks (or seconds)
    """
    days, hour_min_secs = re.split(LLDPD_UPTIME_RE_SPLIT_PATTERN, time_str)
    struct_time = time.strptime(hour_min_secs, LLDPD_TIME_FORMAT)
    time_delta = datetime.timedelta(days=int(days), hours=struct_time.tm_hour, minutes=struct_time.tm_min,
                                    seconds=struct_time.tm_sec)
    return int(time_delta.total_seconds())


class LldpSyncDaemon(SonicSyncDaemon):
    """
    This script uploads lldp information to Redis DB.
    Required lldp counters are kept in a separate database (number 1)
    within the same Redis instance on a switch
    """
    LLDP_ENTRY_TABLE = 'LLDP_ENTRY_TABLE'

    @unique
    class PortIdSubtypeMap(int, Enum):
        """
        This class follows the 802.1AB TEXTUAL-CONVENTION for mapping LLDP subtypes to integers (enum).
        `lldpd` does this as well.  This avoids using regex to parse `lldpd` data.

        From lldpd / src / lib / atoms / port.c:
        static lldpctl_map_t port_id_subtype_map[] = {
            { LLDP_PORTID_SUBTYPE_IFNAME,   "ifname"},
            { LLDP_PORTID_SUBTYPE_IFALIAS,  "ifalias" },
            { LLDP_PORTID_SUBTYPE_LOCAL,    "local" },
            { LLDP_PORTID_SUBTYPE_LLADDR,   "mac" },
            { LLDP_PORTID_SUBTYPE_ADDR,     "ip" },
            { LLDP_PORTID_SUBTYPE_PORT,     "unhandled" },
            { LLDP_PORTID_SUBTYPE_AGENTCID, "unhandled" },
            { 0, NULL},
        };
        """
        ifalias = int(LldpPortIdSubtype.interfaceAlias)
        # port =  LldpPortIdSubtype.portComponent # (unsupported by lldpd)
        mac = int(LldpPortIdSubtype.macAddress)
        ip = int(LldpPortIdSubtype.networkAddress)
        ifname = int(LldpPortIdSubtype.interfaceName)
        # agentcircuitid = int(LldpPortIdSubtype.agentCircuitId) # (unsupported by lldpd)
        local = int(LldpPortIdSubtype.local)

    @unique
    class ChassisIdSubtypeMap(int, Enum):
        """
        This class follows the 802.1AB TEXTUAL-CONVENTION for mapping LLDP subtypes to integers (enum).
        `lldpd` does this as well.  This avoids using regex to parse `lldpd` data.

        From lldpd / src / lib / atoms / chassis.c:
        static lldpctl_map_t chassis_id_subtype_map[] = {
            { LLDP_CHASSISID_SUBTYPE_IFNAME,  "ifname"},
            { LLDP_CHASSISID_SUBTYPE_IFALIAS, "ifalias" },
            { LLDP_CHASSISID_SUBTYPE_LOCAL,   "local" },
            { LLDP_CHASSISID_SUBTYPE_LLADDR,  "mac" },
            { LLDP_CHASSISID_SUBTYPE_ADDR,    "ip" },
            { LLDP_CHASSISID_SUBTYPE_PORT,    "unhandled" },
            { LLDP_CHASSISID_SUBTYPE_CHASSIS, "unhandled" },
            { 0, NULL},
        };
        """
        ifname = int(LldpChassisIdSubtype.interfaceName)
        ifalias = int(LldpChassisIdSubtype.interfaceAlias)
        # port =  int(LldpChassisIdSubtype.portComponent) # (unsupported by lldpd)
        mac = int(LldpChassisIdSubtype.macAddress)
        ip = int(LldpChassisIdSubtype.networkAddress)
        # chassis = int(LldpChassisIdSubtype.chassisComponent) # (unsupported by lldpd)
        local = int(LldpPortIdSubtype.local)

    def __init__(self, update_interval=None):
        super(LldpSyncDaemon, self).__init__()
        self._update_interval = update_interval or DEFAULT_UPDATE_INTERVAL
        self.db_connector = SonicV2Connector()
        self.db_connector.connect(self.db_connector.APPL_DB)

    def source_update(self):
        """
        Invoke lldpctl and format as JSON
        """
        cmd = ['/usr/sbin/lldpctl', '-f', 'json']
        logger.debug("Invoking lldpctl with: {}".format(cmd))

        try:
            # execute the subprocess command
            lldpctl_output = subprocess.check_output(cmd)
        except subprocess.CalledProcessError:
            logger.exception("lldpctl exited with non-zero status")
            return None

        try:
            # parse the scrapped output
            lldpctl_json = json.loads(lldpctl_output)
        except ValueError:
            logger.exception("Failed to parse lldpctl output")
            return None
        else:
            return lldpctl_json

    def parse_update(self, lldp_json):
        """
        Parse lldpd output to extract
        (1) LldpRemPortDesc;
        (2) LldpRemPortID;
        (3) LldpRemPortIdSubtype;
        (4) LldpRemSysName.

        LldpRemEntry ::= SEQUENCE {
              lldpRemTimeMark           TimeFilter,
              *lldpRemLocalPortNum       LldpPortNumber,
              *lldpRemIndex              Integer32,
              lldpRemChassisIdSubtype   LldpChassisIdSubtype,
              lldpRemChassisId          LldpChassisId,
              lldpRemPortIdSubtype      LldpPortIdSubtype,
              lldpRemPortId             LldpPortId,
              lldpRemPortDesc           SnmpAdminString,
              lldpRemSysName            SnmpAdminString,
              lldpRemSysDesc            SnmpAdminString,
              *lldpRemSysCapSupported    LldpSystemCapabilitiesMap,
              *lldpRemSysCapEnabled      LldpSystemCapabilitiesMap
        }
        """
        # TODO: *Implement
        try:
            interface_list = lldp_json['lldp'].get('interface') or []
            parsed_interfaces = defaultdict(dict)
            for interface in interface_list:
                try:
                    # [{'if_name' : { attributes...}}, {'if_other': {...}}, ...]
                    (if_name, if_attributes), = interface.items()
                except AttributeError:
                    # {'if_name' : { attributes...}}, {'if_other': {...}}
                    if_name = interface
                    if_attributes = interface_list[if_name]

                if 'port' in if_attributes:
                    parsed_interfaces[if_name].update(self.parse_port(if_attributes['port']))
                if 'chassis' in if_attributes:
                    parsed_interfaces[if_name].update(self.parse_chassis(if_attributes['chassis']))

                # lldpRemTimeMark           TimeFilter,
                parsed_interfaces[if_name].update({'lldp_rem_time_mark': str(parse_time(if_attributes.get('age')))})

            return parsed_interfaces
        except (KeyError, ValueError):
            logger.exception("Failed to parse LLDPd JSON. \n{}\n -- ".format(lldp_json))

    def parse_chassis(self, chassis_attributes):
        try:
            (rem_name, rem_attributes), = chassis_attributes.items()
            chassis_id_subtype = str(self.ChassisIdSubtypeMap[rem_attributes['id']['type']].value)
            chassis_id = rem_attributes['id']['value']
            rem_desc = rem_attributes.get('descr')
        except (KeyError, ValueError):
            logger.exception("Could not infer system information from: {}".format(chassis_attributes))
            chassis_id_subtype, chassis_id, rem_name, rem_desc = None

        return {
            # lldpRemChassisIdSubtype   LldpChassisIdSubtype,
            'lldp_rem_chassis_id_subtype': chassis_id_subtype,
            # lldpRemChassisId          LldpChassisId,
            'lldp_rem_chassis_id': chassis_id,
            # lldpRemSysName            SnmpAdminString,
            'lldp_rem_sys_name': rem_name,
            # lldpRemSysDesc            SnmpAdminString,
            'lldp_rem_sys_desc': rem_desc,
        }

    def parse_port(self, port_attributes):
        port_identifiers = port_attributes.get('id')
        try:
            subtype = str(self.PortIdSubtypeMap[port_identifiers['type']].value)
            value = port_identifiers['value']

        except ValueError:
            logger.exception("Could not infer chassis subtype from: {}".format(port_attributes))
            subtype, value = None

        return {
            # lldpRemPortIdSubtype      LldpPortIdSubtype,
            'lldp_rem_port_id_subtype': subtype,
            # lldpRemPortId             LldpPortId,
            'lldp_rem_port_id': value,
            # lldpRemSysDesc            SnmpAdminString,
            'lldp_rem_port_desc': port_attributes.get('descr')
        }

    def sync(self, parsed_update):
        """
        Sync LLDP information to redis DB.
        """
        logger.debug("Initiating LLDPd sync to Redis...")
        for interface, if_attributes in parsed_update.items():
            if re.match(SONIC_ETHERNET_RE_PATTERN, interface) is None:
                logger.warning("Ignoring interface '{}'".format(interface))
                continue
            for k, v in if_attributes.items():
                # port_table_key = LLDP_ENTRY_TABLE:INTERFACE_NAME;
                table_key = ':'.join([LldpSyncDaemon.LLDP_ENTRY_TABLE, interface])
                self.db_connector.set(self.db_connector.APPL_DB, table_key, k, v, blocking=True)
            logger.debug("sync'd: \n{}".format(json.dumps(if_attributes, indent=3)))
