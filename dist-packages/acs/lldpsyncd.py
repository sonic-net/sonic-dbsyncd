#!/usr/bin/env python

import os
import re
import getopt
import logging
import subprocess

import pysswsdk.util as util
from dbsyncd import DBSyncd

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class LldpSyncd(DBSyncd):

    '''
        This script uploads lldp information to Redis DB.
        Required lldp counters are kept in a separate database (number 1)
        within the same Redis instance on a switch
    '''

    IF_DB = 'IF_COUNTER_DB'
    LLDP_DB = 'LLDP_COUNTER_DB'

    def __init__(self):

        super(LldpSyncd, self).__init__()
        self.lldp_table = {}

    def get_info(self):
        '''
            Retrieve lldp info via lldpctl
        '''

        cmd = ['/usr/sbin/lldpctl', '-f', 'keyvalue']
        lldpinfo = subprocess.check_output(cmd)
        #logger.info('lldpinfo : %s' %lldpinfo)
        logger.debug('Get lldp info from lldpctl cmd: %s' % lldpinfo)

        if lldpinfo:
            lldpinfo = lldpinfo.split('\n')
        else:
            logger.debug('lldpctl output is empty')

        return lldpinfo

    def parse_info(self, lldpinfo):
        '''
            Parse the lldp information to extract the following info:
            (1) LldpRemPortDesc;
            (2) LldpRemPortID;
            (3) LldpRemPortIdSubtype;
            (4) LldpRemSysName.
        '''

        logger.debug('Parse lldp info')

        # An example lldpinfo entry: lldp.Ethernet.port.descr=ge-0/0/11.0
        # 1) Split eacch lldp entry into two parts: key and value 
        # 2) Extrace the interface index from the key
        #    Please see function update_lldp_table for more explanation. 

        for info in lldpinfo:
            if info.startswith('lldp'):
                key, value = info.strip().split('=', 1)
                key = key.split('.')
                self.update_lldp_table(key, value)

    def update_lldp_table(self, key, value):
        '''
            Update lldp table if the lldpinfo key satisfies the required pattern
        '''

        # An example key is lldp.Ethernet56.port.descr
        # 1) Ethernet56 is ACS-compliant interface name
        # 2) port.descr correspond to the oid name LldpRemPortDescr
        lldp_table_key = self.create_lldp_table_key(key)
        if lldp_table_key is None:
            return

        key_suffix = key[2:] # omitting the first two elements of the key
                             # e.g. key_suffix = {port, descr} 

        # Filter out unneeded entries based on key format. 
        if key_suffix[0] == 'port':
            if key_suffix[1] == 'auto-negotiation':
                return

            if key_suffix[1] == 'mfs':
                return

            if key_suffix[1] == 'descr':
                self.add_lldp_entry(lldp_table_key, 'LldpRemPortDescr', value)
                return

            # lldpctl combines LldpRemPortID and LldpRemPortSubtype in one keyvalue pair
            # e.g. lldp.Ethernet56.port.local=525, where port subtype is local and port id is 525
            self.add_lldp_entry(lldp_table_key, 'LldpRemPortIdSubtype', key_suffix[1])
            self.add_lldp_entry(lldp_table_key, 'LldpRemPortID', value)

        elif key_suffix[0] == 'chassis' and key_suffix[1] == 'name':
            self.add_lldp_entry(lldp_table_key, 'LldpRemSysName', value)


    def add_lldp_entry(self, lldp_table_key, lldp_info_key, value):
        '''
            Add the keyvalue pair (lldp_info_key, value) as an entry indexed by lldp_table_key
            to the local lldp_table 
        '''

        logger.debug('Add an lldp entry to local lldp_table - lldp_table_key:%s, lldp_info_key:%s, value:%s' 
                     % (lldp_table_key, lldp_info_key, value))

        if lldp_table_key not in self.lldp_table:
            self.lldp_table[lldp_table_key] = {}
            self.lldp_table[lldp_table_key][lldp_info_key] = value
        else:
            self.lldp_table[lldp_table_key][lldp_info_key] = value
            

    def create_lldp_table_key(self, key):
        '''
           Use interface/port SAI IDs as keys for lldp_table
        '''

        if_name = key[1]
        logger.debug('create_lldp_table_key: if_name:%s' % if_name)

        # Ignore management port eth0. This info is currently not stored in Redis
        if if_name == 'eth0':
            return

        match = re.match('^Ethernet(\d+)(_\d+)?$', if_name)
        if match:
            index = match.group(1) # How will the index influenced by the second group of digits?
            lldp_table_key = self.get_port_sid(if_name)
            return lldp_table_key
        logger.exception('Unable to match interface name %s to known pattern', if_name)
        raise Exception('Unable to match interface name %s to known pattern', if_name)

    def upload_to_redis(self):
        '''
            Upload lldp info to Redis database
        '''

        logger.debug('Upload lldp info to Redis: %s' % self.lldp_table)
        for (lldp_table_key, lldp_entries) in self.lldp_table.iteritems():                 
            for (lldp_info_key, val) in lldp_entries.iteritems():
                logger.debug('lldp info - key:%s, val:%s' % (lldp_info_key, val))
                self.db_connector.set(LldpSyncd.LLDP_DB, lldp_table_key, lldp_info_key, val, blocking=True)  


    def get_port_sid(self, if_name):
        '''
            Get the SAI ID of interface if_name from 
            the port_name_map
        '''

        port_sid = self.port_name_map[if_name]
        logger.debug('get_port_sid: port_sid:%s' % port_sid)
        return port_sid


def main():

    util.setup_logging('data/lldpsyncd_logging.json')

    lldp_syncd = None

    try:
        args = util.process_options(os.path.basename(__file__))

        lldp_syncd = LldpSyncd()

        log_level = args.get('log_level')
        update_frequency = args.get('update_frequency')
        if log_level:
            lldp_syncd.logger.setLevel(log_level)
        if update_frequency:
            lldp_syncd.update_frequency = update_frequency

        db_list = [LldpSyncd.IF_DB, LldpSyncd.LLDP_DB]
        lldp_syncd.connect_to_redis(db_list)
        lldp_syncd.get_port_name_map(LldpSyncd.IF_DB)
        logger.info('Start lldpsyncd...')
        lldp_syncd.start()
    except getopt.GetoptError as e:
        logger.error(e)
    except KeyboardInterrupt:
        lldp_syncd.stop_dbsyncd()
    except Exception as e:
        logger.exception('Unhandled exception:%s', e)
        if lldp_syncd is not None:
            lldp_syncd.stop_dbsyncd()


if __name__=="__main__":

    main()
