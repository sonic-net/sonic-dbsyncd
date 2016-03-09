import sys
import unittest
from parse import *
from inspect import getfile, currentframe
from os.path import join, dirname, abspath
from mockredis import mock_strict_redis_client

import pysswsdk.dbconnector as dbconnector

############ Append the source code directory path of lldpsyncd to system path ##########
curr_dir_path = dirname(abspath(getfile(currentframe())))
upper_dir_path = dirname(curr_dir_path)
src_dir_path = join(upper_dir_path, 'dist-packages/acs')
sys.path.append(src_dir_path)
#########################################################################################

import lldpsyncd

class TestLldpSyncd(unittest.TestCase):

    def get_full_path(self, file_name):
        '''
            Get the full path of File %file_name
        '''

        curr_path = dirname(abspath(getfile(currentframe())))
        file_path = join(curr_path, file_name)
        return file_path

    def load_port_name_map(self, client, file_name, table_name):
        '''
            Upload the desired port_name_map to the mock redis
            The test scenario is determined by file_name
        '''

        file_path = self.get_full_path(file_name)
        with open(file_path, 'r') as f:
            for line in f:
                (key, val) = line.strip().split(', ')
                client.hset(table_name, key, val)

    def load_lldp_info(self, file_name):
        '''
            Upload the lldp counter information to the mock redis
            The test scenario is determined by file_name
        '''

        self.lldp_info = []
        file_path = self.get_full_path(file_name)
        with open(file_path, 'r') as f:
            for line in f:
                self.lldp_info.append(line)

    def search_lldp_info(self, pattern, lldpctl_input, lldp_counter_key, 
                         port_subtype=None):
        '''
            parse the lldpctl_input line according the specified pattern
            This extracts the interface name and counter value
            Then we add the lldp counter info to local lldp table
            Special treatment for port subtype is needed
        '''

        result = parse(pattern, lldpctl_input)
        if result is not None:
            if_name = result[0]
            lldp_counter_value = result[1]
            lldp_counter_entry = {lldp_counter_key: lldp_counter_value}
            self.add2_loc_lldp_table(if_name, lldp_counter_entry)
            if port_subtype is not None:
               port_subtype_entry = {'LldpRemPortIdSubtype': port_subtype}
               self.add2_loc_lldp_table(if_name, port_subtype_entry)
            return True
        return False

    def add2_loc_lldp_table(self, key, content):
        '''
            Add the key value pair to local lldp table
            This local record is used to compare with Redis record
        '''

        if self.loc_lldp_table.get(key) is None:
            self.loc_lldp_table[key] = {}
        self.loc_lldp_table[key].update(content)

    def parse_lldp_info(self):
        '''
            Parse lldp info to keep local record
        '''

        self.loc_lldp_table = {}
        for info in self.lldp_info:
            succ = self.search_lldp_info('lldp.{}.chassis.name={}', info, 'LldpRemSysName')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.descr={}', info, 'LldpRemPortDescr')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.ifname={}', info, 'LldpRemPortID', 
                                         port_subtype='ifname')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.local={}', info, 'LldpRemPortID',
                                         port_subtype='local')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.macaddress={}', info, 'LldpRemPortID',
                                         port_subtype='macaddress')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.ifalias={}', info, 'LldpRemPortID',
                                         port_subtype='ifalias')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.networkaddress={}', info, 'LldpRemPortID',
                                         port_subtype='networkaddress')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.portcomponent={}', info, 'LldpRemPortID',
                                         port_subtype='portcomponent')
            if succ:
                continue

            succ = self.search_lldp_info('lldp.{}.port.agentcircuitid={}', info, 'LldpRemPortID',
                                         port_subtype='agentcircuitid')
            if succ:
                continue

    def get_loc_lldp_info(self, port, oid_name):
        '''
            Get the value for oid_name from local record
        '''

        lldp_entry = self.loc_lldp_table.get(port)
        if lldp_entry is not None:
            lldpinfo = lldp_entry.get(oid_name)
            return lldpinfo
        return

    def setup(self, port_name_map_fname='port_name_map_short.txt', lldp_info_fname='lldp_info.txt'):
        '''
            Set up redis databses.
            The testing scenarios can be changed by setting port_name_map_fname
            and lldp_info_fname to desired files.
            By default, they are set to specified values above
        '''

        self.setup_dbconnector(port_name_map_fname)
        self.setup_lldpsyncd(lldp_info_fname)
        
    def setup_dbconnector(self, file_name):
        '''
            Set up the DBconnector instance by mocking its redis client
            and load the desired port_name_map
        '''
               
        dbconnector.DBConnector.setup()
        self.db_connector = dbconnector.DBConnector()
        ifdb_id = dbconnector.DBConnector.get_dbid(lldpsyncd.LldpSyncd.IF_DB)
        ifdb_client = mock_strict_redis_client(host=dbconnector.DBConnector.LOCAL_HOST,
                                               port=dbconnector.DBConnector.REDIS_PORT,
                                               db=ifdb_id)
        # load port name map to ifdb_client
        self.load_port_name_map(ifdb_client, file_name, 'port_name_map')

        lldpdb_id = dbconnector.DBConnector.get_dbid(lldpsyncd.LldpSyncd.LLDP_DB)
        lldpdb_client =  mock_strict_redis_client(host=dbconnector.DBConnector.LOCAL_HOST,
                                                  port=dbconnector.DBConnector.REDIS_PORT,
                                                  db=lldpdb_id)

        self.db_connector.redis_client = {lldpsyncd.LldpSyncd.IF_DB: ifdb_client,
                                          lldpsyncd.LldpSyncd.LLDP_DB: lldpdb_client}

    def setup_lldpsyncd(self, file_name):
        '''
            Set up the LldpSyncd instance
            by instantiating its db_connector object to tailor one via setup_dbconnector
            and loading the desired the lldp info file
        '''

        self.lldp_syncd = lldpsyncd.LldpSyncd()
        self.lldp_syncd.db_connector = self.db_connector
        self.lldp_syncd.get_port_name_map(lldpsyncd.LldpSyncd.IF_DB)

        self.load_lldp_info(file_name)
        self.parse_lldp_info()
        self.lldp_syncd.parse_info(self.lldp_info)
        self.lldp_syncd.upload_to_redis()

    def record_correct(self, oid_name):
        '''
            Check whether there Redis record for oid_name
            is the same as the local record
        '''

        for port in self.lldp_syncd.port_name_map:
            port_sid = self.lldp_syncd.get_port_sid(port)
            redis_lldp_info = self.db_connector.get(lldpsyncd.LldpSyncd.LLDP_DB, port_sid, oid_name, blocking=False)
            local_lldp_info = self.get_loc_lldp_info(port, oid_name)
            self.assertEqual(redis_lldp_info.lower(), local_lldp_info.lower())

    def record_not_exists(self, oid_name):
         '''
             Check whether UnvailableDataError is raised when a record
             does not exist for oid_name
         '''

         for port in self.lldp_syncd.port_name_map:
            port_sid = self.lldp_syncd.get_port_sid(port)
            lldp_info = self.db_connector.get(lldpsyncd.LldpSyncd.LLDP_DB, port_sid, oid_name, blocking=False)
            self.assertRaises(dbconnector.UnavailableDataError)

    def test_PortNameMap(self):
        '''
            Test whether port_name_map is loaded
        '''

        self.setup()
        assert self.lldp_syncd.port_name_map is not None

    def test_NumOfInterfaces(self):
        '''
            Test whether the number of LLDP entries in LLDP_DB 
            equals the number of interfaces specified in the port_name_map
        '''

        self.setup()
        if_num = len(self.lldp_syncd.port_name_map)
        lldp_entries = len(self.lldp_syncd.db_connector.keys(lldpsyncd.LldpSyncd.LLDP_DB, blocking=False))
        self.assertEqual(if_num, lldp_entries) 
        
    def test_NoLldpRemPortDescr(self, fname='lldp_info_noportdescr.txt'):
        '''
            Negative test for LldpRemPortDescr
        '''

        self.setup(lldp_info_fname=fname)
        self.record_not_exists('LldpRemPortDescr')        

    def test_LldpRemPortDescr(self):
        '''
            Positive test for LldpRemPortDescr
        '''

        self.setup()
        self.record_correct('LldpRemPortDescr')

    def test_NoLldpRemPortID(self, fname='lldp_info_noportid.txt'):
        '''
            Negative test for LldpRemPortID
        '''

        self.setup(lldp_info_fname=fname)
        self.record_not_exists('LldpRemPortID')

    def test_LldpRemPortID(self):
        '''
            Positive test for LldpRemPortID
        '''

        self.setup()
        self.record_correct('LldpRemPortID')

    def test_NoLldpRemPortIdSubtype(self, fname='lldp_info_noportid.txt'):
        '''
            Negative test for LldpRemPortSubtype
        '''

        self.setup(lldp_info_fname=fname)
        self.record_not_exists('LldpRemPortIdSubtype')

    def test_LldpRemPortSubtype(self):
        '''
            Positive test for LldpRemPortSubtype
        '''

        self.setup()
        self.record_correct('LldpRemPortIdSubtype')

    def test_NoLldpRemSysName(self, fname='lldp_info_nosysname.txt'):
        '''
            Negative test for LldpRemSysName
        '''

        self.setup(lldp_info_fname=fname)
        self.record_not_exists('LldpRemSysName')

    def test_LldpRemSysName(self):
        '''
            Positive test for LldpRemPortSysName
        '''

        self.setup()
        self.record_correct('LldpRemSysName')

if __name__ == "__main__":
    unittest.main()
