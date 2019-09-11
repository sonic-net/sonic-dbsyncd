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
from .conventions import LldpPortIdSubtype, LldpChassisIdSubtype, LldpSystemCapabilitiesMap

LLDPD_TIME_FORMAT = '%H:%M:%S'

DEFAULT_UPDATE_INTERVAL = 10

SONIC_ETHERNET_RE_PATTERN = r'^(Ethernet(\d+)|eth0)$'
LLDPD_UPTIME_RE_SPLIT_PATTERN = r' days?, '


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
    time_delta = datetime.timedelta(days=int(days), hours=struct_time.tm_hour,
                                    minutes=struct_time.tm_min,
                                    seconds=struct_time.tm_sec)
    return int(time_delta.total_seconds())


class LldpSyncDaemon(SonicSyncDaemon):
    """
    This script uploads lldp information to Redis DB.
    Required lldp counters are kept in a separate database (number 1)
    within the same Redis instance on a switch
    """
    LLDP_ENTRY_TABLE = 'LLDP_ENTRY_TABLE'
    LLDP_LOC_CHASSIS_TABLE = 'LLDP_LOC_CHASSIS'

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

    def get_sys_capability_list(self, if_attributes):
        """
        Get a list of capabilities from interface attributes dictionary.
        :param if_attributes: interface attributes
        :return: list of capabilities
        """
        try:
            # [{'enabled': ..., 'type': 'capability1'}, {'enabled': ..., 'type': 'capability2'}]
            if 'capability' in if_attributes['chassis']:
                capability_list = if_attributes['chassis']['capability']
            else:
                capability_list = if_attributes['chassis'].values()[0]['capability']
            # {'enabled': ..., 'type': 'capability'}
            if isinstance(capability_list, dict):
                capability_list = [capability_list]
        except KeyError:
            logger.error("Failed to get system capabilities")
            return []
        return capability_list

    def parse_sys_capabilities(self, capability_list, enabled=False):
        """
        Get a bit map of capabilities, accoding to textual convention.
        :param capability_list: list of capabilities
        :param enabled: if true, consider only the enabled capabilities
        :return: string representing a bit map
        """
        # chassis is incomplete, missing capabilities
        if not capability_list:
            return ""

        sys_cap = 0x00
        for capability in capability_list:
            try:
                if (not enabled) or capability["enabled"]:
                    sys_cap |= 128 >> LldpSystemCapabilitiesMap[capability["type"].lower()]
            except KeyError:
                logger.debug("Unknown capability {}".format(capability["type"]))
        return "%0.2X 00" % sys_cap

    def __init__(self, update_interval=None):
        super(LldpSyncDaemon, self).__init__()
        self._update_interval = update_interval or DEFAULT_UPDATE_INTERVAL
        self.db_connector = SonicV2Connector()
        self.db_connector.connect(self.db_connector.APPL_DB)

        self.chassis_cache = {}
        self.interfaces_cache = {}

    @staticmethod
    def _scrap_output(cmd):
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

        return lldpctl_json

    def source_update(self):
        """
        Invoke lldpctl and format as JSON
        """
        cmd = ['/usr/sbin/lldpctl', '-f', 'json']
        logger.debug("Invoking lldpctl with: {}".format(cmd))
        cmd_local = ['/usr/sbin/lldpcli', '-f', 'json', 'show', 'chassis']
        logger.debug("Invoking lldpcli with: {}".format(cmd_local))

        lldp_json = self._scrap_output(cmd)
        lldp_json['lldp_loc_chassis'] = self._scrap_output(cmd_local)

        return lldp_json

    def parse_update(self, lldp_json):
        """
        Parse lldpd output to extract
        (1) LldpRemPortDesc;
        (2) LldpRemPortID;
        (3) LldpRemPortIdSubtype;
        (4) LldpRemSysName.

        LldpRemEntry ::= SEQUENCE {
              lldpRemTimeMark           TimeFilter,
              lldpRemLocalPortNum       LldpPortNumber,
              lldpRemIndex              Integer32,
              lldpRemChassisIdSubtype   LldpChassisIdSubtype,
              lldpRemChassisId          LldpChassisId,
              lldpRemPortIdSubtype      LldpPortIdSubtype,
              lldpRemPortId             LldpPortId,
              lldpRemPortDesc           SnmpAdminString,
              lldpRemSysName            SnmpAdminString,
              lldpRemSysDesc            SnmpAdminString,
              lldpRemSysCapSupported    LldpSystemCapabilitiesMap,
              lldpRemSysCapEnabled      LldpSystemCapabilitiesMap
        }
        """
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
                    rem_port_keys = ('lldp_rem_port_id_subtype',
                                     'lldp_rem_port_id',
                                     'lldp_rem_port_desc')
                    parsed_port = zip(rem_port_keys, self.parse_port(if_attributes['port']))
                    parsed_interfaces[if_name].update(parsed_port)

                if 'chassis' in if_attributes:
                    rem_chassis_keys = ('lldp_rem_chassis_id_subtype',
                                        'lldp_rem_chassis_id',
                                        'lldp_rem_sys_name',
                                        'lldp_rem_sys_desc',
                                        'lldp_rem_man_addr')
                    parsed_chassis = zip(rem_chassis_keys,
                                         self.parse_chassis(if_attributes['chassis']))
                    parsed_interfaces[if_name].update(parsed_chassis)

                # lldpRemTimeMark           TimeFilter,
                parsed_interfaces[if_name].update({'lldp_rem_time_mark':
                                                   str(parse_time(if_attributes.get('age')))})

                # lldpRemIndex
                parsed_interfaces[if_name].update({'lldp_rem_index': str(if_attributes.get('rid'))})

                capability_list = self.get_sys_capability_list(if_attributes)
                # lldpSysCapSupported
                parsed_interfaces[if_name].update({'lldp_rem_sys_cap_supported':
                                                   self.parse_sys_capabilities(capability_list)})
                # lldpSysCapEnabled
                parsed_interfaces[if_name].update({'lldp_rem_sys_cap_enabled':
                                                   self.parse_sys_capabilities(
                                                       capability_list, enabled=True)})
                if lldp_json['lldp_loc_chassis']:
                    loc_chassis_keys = ('lldp_loc_chassis_id_subtype',
                                        'lldp_loc_chassis_id',
                                        'lldp_loc_sys_name',
                                        'lldp_loc_sys_desc',
                                        'lldp_loc_man_addr')
                    parsed_chassis = dict(zip(loc_chassis_keys,
                                         self.parse_chassis(lldp_json['lldp_loc_chassis']
                                                            ['local-chassis']['chassis'])))

                    loc_capabilities = self.get_sys_capability_list(lldp_json['lldp_loc_chassis']
                                                                    ['local-chassis'])
                    # lldpLocSysCapSupported
                    parsed_chassis.update({'lldp_loc_sys_cap_supported':
                                          self.parse_sys_capabilities(loc_capabilities)})
                    # lldpLocSysCapEnabled
                    parsed_chassis.update({'lldp_loc_sys_cap_enabled':
                                          self.parse_sys_capabilities(loc_capabilities, enabled=True)})

                    parsed_interfaces['local-chassis'].update(parsed_chassis)

            return parsed_interfaces
        except (KeyError, ValueError):
            logger.exception("Failed to parse LLDPd JSON. \n{}\n -- ".format(lldp_json))

    def parse_chassis(self, chassis_attributes):
        try:
            if 'id' in chassis_attributes and 'id' not in chassis_attributes['id']:
                sys_name = ''
                attributes = chassis_attributes
                id_attributes = chassis_attributes['id']
            else:
                (sys_name, attributes) = chassis_attributes.items()[0]
                id_attributes = attributes.get('id', '')

            chassis_id_subtype = str(self.ChassisIdSubtypeMap[id_attributes['type']].value)
            chassis_id = id_attributes.get('value', '')
            descr = attributes.get('descr', '')
            mgmt_ip = attributes.get('mgmt-ip', '')
            if isinstance(mgmt_ip, list):
                mgmt_ip = ','.join(mgmt_ip)
        except (KeyError, ValueError):
            logger.exception("Could not infer system information from: {}"
                             .format(chassis_attributes))
            chassis_id_subtype = chassis_id = sys_name = descr = mgmt_ip = ''

        return (chassis_id_subtype,
                chassis_id,
                sys_name,
                descr,
                mgmt_ip,
                )

    def parse_port(self, port_attributes):
        port_identifiers = port_attributes.get('id')
        try:
            subtype = str(self.PortIdSubtypeMap[port_identifiers['type']].value)
            value = port_identifiers['value']

        except ValueError:
            logger.exception("Could not infer chassis subtype from: {}".format(port_attributes))
            subtype, value = None

        return (subtype,
                value,
                port_attributes.get('descr', ''),
                )

    def cache_diff(self, cache, update):
        """
        Find difference in keys between update and local cache dicts
        :param cache: Local cache dict
        :param update: Update dict
        :return: new, changed, deleted keys tuple
        """
        new_keys = list(set(update.keys()) - set(cache.keys()))
        changed_keys = list(set(key for key in set(update.keys()) & set(cache.keys()) if update[key] != cache[key]))
        deleted_keys = list(set(cache.keys()) - set(update.keys()))

        return new_keys, changed_keys, deleted_keys

    def sync(self, parsed_update):
        """
        Sync LLDP information to redis DB.
        """
        logger.debug("Initiating LLDPd sync to Redis...")

        # push local chassis data to APP DB
        if parsed_update.has_key('local-chassis'):
            chassis_update = parsed_update.pop('local-chassis')
            if chassis_update != self.chassis_cache:
                self.db_connector.delete(self.db_connector.APPL_DB,
                                         LldpSyncDaemon.LLDP_LOC_CHASSIS_TABLE)
                for k, v in chassis_update.items():
                    self.db_connector.set(self.db_connector.APPL_DB,
                                          LldpSyncDaemon.LLDP_LOC_CHASSIS_TABLE, k, v, blocking=True)
                logger.debug("sync'd: {}".format(json.dumps(chassis_update, indent=3)))

        new, changed, deleted = self.cache_diff(self.interfaces_cache, parsed_update)
        self.interfaces_cache = parsed_update
        # Delete LLDP_ENTRIES which were modified or are missing
        for interface in changed + deleted:
            table_key = ':'.join([LldpSyncDaemon.LLDP_ENTRY_TABLE, interface])
            self.db_connector.delete(self.db_connector.APPL_DB, table_key)
        # Repopulate LLDP_ENTRY_TABLE by adding all changed elements
        for interface in changed + new:
            if re.match(SONIC_ETHERNET_RE_PATTERN, interface) is None:
                logger.warning("Ignoring interface '{}'".format(interface))
                continue
            # port_table_key = LLDP_ENTRY_TABLE:INTERFACE_NAME;
            table_key = ':'.join([LldpSyncDaemon.LLDP_ENTRY_TABLE, interface])
            for k, v in parsed_update[interface].items():
                self.db_connector.set(self.db_connector.APPL_DB, table_key, k, v, blocking=True)
            logger.debug("sync'd: \n{}".format(json.dumps(parsed_update[interface], indent=3)))
