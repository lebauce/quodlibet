# -*- coding: utf-8 -*-
# Copyright 2012 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from quodlibet.qltk.data_editors import JSONBasedEditor
from quodlibet.util.json_data import JSONObjectDict
from quodlibet import config

from tests.plugin import PluginTestCase


CustomCommands = Command = None


class TCustomCommands(PluginTestCase):
    """Test CustomCommands plugin and associated classes"""

    def setUp(self):
        globals().update(vars(self.modules["CustomCommands"]))
        config.init()
        self.cmd_list = CustomCommands.DEFAULT_COMS
        self.commands = JSONObjectDict.from_list(self.cmd_list)

    def tearDown(self):
        config.quit()

    def test_JSONBasedEditor(self):
        ed = JSONBasedEditor(Command, self.commands, None, "title")
        ed.show_now()
        ed.destroy()
