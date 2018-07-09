import subprocess
from swsssdk import ConfigDBConnector

from sonic_syncd import SonicSyncDaemon
from . import logger


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

    def run(self):
        self.port_table = self.config_db.get_table('PORT')
        # supply LLDP_LOC_ENTRY_TABLE and lldpd with correct values on start
        for port_name, attributes in self.port_table.items():
            self.run_command("lldpcli configure lldp portidsubtype local {} description '{}'"
                             .format(port_name, attributes.get("description", " ")))

        # subscribe for further changes
        self.config_db.subscribe('PORT', lambda table, key, data:
                                 self.port_handler(key, data))

        logger.info("[lldp dbsyncd] Subscribed to configdb PORT table")
        self.config_db.listen()
