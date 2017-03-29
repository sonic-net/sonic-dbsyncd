import logging.handlers
import sys

import swsssdk.util

import lldp_syncd
import sonic_syncd

LOG_FORMAT = "lldp-syncd [%(name)s] %(levelname)s: %(message)s"

# import command line arguments
args = swsssdk.util.process_options("lldp_syncd")

# configure logging. If debug is specified, logs to stdout at designated level. syslog otherwise.
log_level = args.get('log_level')
if log_level is None:
    syslog_handler = logging.handlers.SysLogHandler(address='/dev/log',
                                                    facility=logging.handlers.SysLogHandler.LOG_DAEMON)
    syslog_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    lldp_syncd.logger.addHandler(syslog_handler)
    log_level = logging.INFO
else:
    lldp_syncd.logger.addHandler(logging.StreamHandler(sys.stdout))

# set the log levels
swsssdk.logger.setLevel(log_level)
sonic_syncd.logger.setLevel(log_level)
lldp_syncd.logger.setLevel(log_level)

# inherit logging handlers in submodules
swsssdk.logger.handlers = lldp_syncd.logger.handlers
sonic_syncd.logger.handlers = lldp_syncd.logger.handlers

#
# Logging configuration complete. Enter main runtime.
#
from .main import main

main(update_frequency=args.get('update_frequency'))
