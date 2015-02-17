# -*- coding: utf-8 -*-
# Copyright 2006 Joe Wreschnig
#           2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os


import gi
gi.require_version("Gio", "2.0")

from gi.repository import Gio

from quodlibet import app
from quodlibet.plugins.events import EventPlugin


class AutoMasking(EventPlugin):
    PLUGIN_ID = "automask"
    PLUGIN_NAME = _("Automatic Masking")
    PLUGIN_DESC = _("Automatically masks and unmasks drives when they "
                    "are unmounted or mounted.")

    __sigs = None
    __monitor = None

    def enabled(self):
        if self.__monitor is None:
            self.__monitor = Gio.VolumeMonitor.get()
            self.__sigs = [
                self.__monitor.connect('mount-added', self.__mounted),
                self.__monitor.connect('mount-removed', self.__unmounted),
                ]
        else:
            for signal_id in self.__sigs:
                self.__monitor.handler_unblock(signal_id)

    def disabled(self):
        for signal_id in self.__sigs:
            self.__monitor.handler_unblock(signal_id)

    def __mounted(self, monitor, mount):
        path = mount.get_default_location().get_path()
        if path is not None:
            app.library.unmask(os.path.normpath(path))

    def __unmounted(self, monitor, mount):
        path = mount.get_default_location().get_path()
        if path is not None:
            app.library.mask(os.path.normpath(path))
