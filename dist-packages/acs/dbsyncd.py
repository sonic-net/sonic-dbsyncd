import time
import threading

import logging
import logging.config

import pysswsdk.util as util
from pysswsdk.dbconnector import DBConnector

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class DBSyncd(threading.Thread):
    '''
        The base class for all DB sync daemons
    '''

    # Default values

    # Update frequency in seconds
    FREQ = 20

    LOG_LEVEL = logging.INFO

    def __init__(self):

        super(DBSyncd, self).__init__()

        self.stop_event = threading.Event()
        self.update_frequency = DBSyncd.FREQ

        DBConnector.setup()
        self.db_connector = DBConnector()

    def connect_to_redis(self, db_list):
        '''
            Connect to Redis databases  via dbconnector
        '''

        logger.info('Connect to Redis databases %s' %db_list)

        for db_name in db_list:
            self.db_connector.connect(db_name)

    def get_port_name_map(self, db_name):      
        '''
            Retrieving the port_name_map from Redis
        '''
        
        self.port_name_map = self.db_connector.get_all(db_name, 
                                                       'port_name_map', 
                                                       blocking=True)

    # Override this
    def get_info(self):
        '''
            Get the required info that needs to be synced to Redis
            can be override by subclasses
        '''
        pass

    # Override this
    def parse_info(self, info):
        '''
            The retrieved info needs to be parsed
            to get desired states
        '''
        pass

    # Override this
    def upload_to_redis(self):
        '''
            Upload desired states to Redis
        '''
        pass

    def run(self):

        while True:
            if self.stop_event.is_set(): break
            info = self.get_info()
            if info:
                self.parse_info(info)
                self.upload_to_redis()
            time.sleep(self.update_frequency)

    def stop_dbsyncd(self):
        '''
            Stop DBSyncd
        '''

        self.stop_event.set()
