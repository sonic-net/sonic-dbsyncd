import subprocess
import re
from swsssdk import ConfigDBConnector

from sonic_syncd import SonicSyncDaemon
from . import logger

MGMT_INTERFACE_PATTERN = r"MGMT_INTERFACE*"
IPV4_PATTERN = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'


class DBSyncDaemon(SonicSyncDaemon):
    """
    A Thread that listens to changes in CONFIG DB,
    and contains handlers to configure lldpd accordingly.
    """

    def __init__(self):
        super(DBSyncDaemon, self).__init__()
        self.config_db = ConfigDBConnector()
        self.config_db.connect()
        logger.info("[lldp dbsyncd] Connected to configdb")
        self.port_table = {}
        self.man_addr = None

    def run_command(self, command):
        p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        stdout = p.communicate()[0]
        p.wait()
        if p.returncode != 0:
            logger.error("[lldp dbsyncd] command execution returned {}. "
                         "Command: '{}', stdout: '{}'".format(p.returncode, command, stdout))

    def port_handler(self, key, data):
        """
        Handle updates in 'PORT' table.
        """
        # we're interested only in description for now
        if self.port_table[key].get("description") != data.get("description"):
            new_descr = data.get("description", " ")
            logger.info("[lldp dbsyncd] Port {} description changed to {}."
                        .format(key, new_descr))
            self.run_command("lldpcli configure lldp portidsubtype local {} description '{}'"
                             .format(key, new_descr))
        # update local cache
        self.port_table[key] = data

    def man_addr_init(self):

        man_table = self.config_db.get_table('MGMT_INTERFACE')
        # example table:
        # {('eth0', 'FC00:2::32/64'): {'forced_mgmt_routes': ['10.0.0.100/31'], 'gwaddr': 'fc00:2::fe'},
        # ('eth0', '10.224.23.69/24'): {'gwaddr': '10.224.23.254'}}
        mgmt_ips = [i[1].split('/')[0] for i in man_table.keys()]
        ipv4_mgmt_ips = [i for i in mgmt_ips if re.match(IPV4_PATTERN, i)]
        try:
            self.run_command("lldpcli configure system ip management pattern {}"
                             .format(ipv4_mgmt_ips[0]))
            logger.debug("Configured lldpd with {} local management ip".format(ipv4_mgmt_ips[0]))
        except IndexError:
            logger.error("No IPv4 management interface found")

    def port_table_init(self):
        self.port_table = self.config_db.get_table('PORT')
        # supply LLDP_LOC_ENTRY_TABLE and lldpd with correct values on start
        for port_name, attributes in self.port_table.items():
            self.run_command("lldpcli configure lldp portidsubtype local {} description '{}'"
                             .format(port_name, attributes.get("description", " ")))

    def run(self):

        self.port_table_init()
        # subscribe for further changes
        self.config_db.subscribe('PORT', lambda table, key, data:
                                 self.port_handler(key, data))

        self.man_addr_init()

        logger.info("[lldp dbsyncd] Subscribed to configdb PORT table")
        self.config_db.listen()
