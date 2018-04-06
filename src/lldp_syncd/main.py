from . import logger
from .daemon import LldpSyncDaemon
from .dbsyncd import DBSyncDaemon

DEFAULT_UPDATE_FREQUENCY = 10


def main(update_frequency=None):
    try:
        lldp_syncd = LldpSyncDaemon(update_frequency or DEFAULT_UPDATE_FREQUENCY)
        logger.info('Starting SONiC LLDP sync daemon...')
        dbsyncd = DBSyncDaemon()
        lldp_syncd.start()
        dbsyncd.start()
        lldp_syncd.join()
        dbsyncd.join()
    except KeyboardInterrupt:
        logger.info("ctrl-C captured, shutting down.")
    except Exception:
        logger.exception('Uncaught exception')
    finally:
        if 'lldp_syncd' in locals():
            lldp_syncd.stop()
