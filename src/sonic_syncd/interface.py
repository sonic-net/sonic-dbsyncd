import threading
import time

from . import logger

DEFAULT_UPDATE_FREQUENCY = 10


class SonicSyncDaemon(threading.Thread):
    """
    SONiC sync daemon interface.
    """

    def __init__(self, update_frequency=None):
        """
        :param update_frequency: How long to wait before executing the update task (in seconds).
        """
        super(SonicSyncDaemon, self).__init__(name=self.__class__.__name__)
        self._update_frequency = update_frequency or DEFAULT_UPDATE_FREQUENCY
        self.run_event = threading.Event()

    def source_update(self):
        """
        Update the source that is to be synced to Redis. Must return a JSON-like object.
        """
        raise NotImplementedError()

    def parse_update(self, update_obj):
        """
        Parse the update object.
        """
        raise NotImplementedError()

    def sync(self, parsed_update):
        """
        Save and/or store the parsed update.
        """
        raise NotImplementedError()

    def run(self):
        self.run_event.set()
        while self.run_event.is_set():
            update_obj = self.source_update()
            if update_obj is not None:
                parsed_update = self.parse_update(update_obj)
                if parsed_update is not None:
                    self.sync(parsed_update)
                else:
                    logger.warning("No parsed information returned. Skipping sync.")
            else:
                logger.warning("No source information returned during last update. Skipping sync.")
            time.sleep(self._update_frequency)

    def stop(self):
        """
        Stop DBSyncd
        """
        self.run_event.clear()
