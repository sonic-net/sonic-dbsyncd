#!/usr/bin/env python3
"""Host Service to handle docker-to-host communication"""

import os
import os.path
import glob
import importlib
import sys

import dbus
import dbus.service
import dbus.mainloop.glib

from gi.repository import GObject

def find_module_path():
    """Find path for host_moduels"""
    try:
        from host_modules import host_service
        return os.path.dirname(host_service.__file__)
    except ImportError as e:
        return None

def register_modules(mod_path):
    """Register all host modules"""
    sys.path.append(mod_path)
    for mod_file in glob.glob(os.path.join(mod_path, '*.py')):
        if os.path.isfile(mod_file) and not mod_file.endswith('__init__.py'):
            mod_name = os.path.basename(mod_file)[:-3]
            module = importlib.import_module(mod_name)

            register_cb = getattr(module, 'register', None)
            if not register_cb:
                raise Exception('Missing register function for ' + mod_name)

            register_dbus(register_cb)
