# -*- coding: utf-8 -*-
# Copyright 2012,2013 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import sys
from optparse import OptionParser

from quodlibet.formats import MusicFile


class CommandError(Exception):
    pass


class Command(object):
    """Base class for commands.

    Subclasses can override _add_options() and _execute()
    """

    NAME = None
    DESCRIPTION = None
    USAGE = None
    COMMANDS = []

    @classmethod
    def register(cls, cmd_cls):
        cls.COMMANDS.append(cmd_cls)
        cls.COMMANDS.sort(key=lambda c: c.NAME)

    def __init__(self, main_cmd, options=None):
        self._main_cmd = main_cmd
        usage = "%s %s %s" % (main_cmd, self.NAME, self.USAGE)
        self.__parser = OptionParser(usage=usage, description=self.DESCRIPTION)
        if options is None:
            options = self.__parser.parse_args([])[0]
        self.__options = options
        self._add_options(self.__parser)

    def _add_options(self, parser):
        """Override to add options to the parser"""

        pass

    @property
    def verbose(self):
        return self.__options.verbose

    @verbose.setter
    def verbose(self, value):
        self.__options.verbose = bool(value)

    def log(self, text):
        """Print output if --verbose was passed"""

        if self.verbose:
            return print_(text, sys.stderr)

    def load_song(self, path):
        """Load a song. Raises CommandError in case it fails"""

        self.log("Load file: %r" % path)
        song = MusicFile(path)
        if not song:
            raise CommandError(_("Failed to load file: %r") % path)
        return song

    def save_songs(self, songs):
        """Save all passed songs"""

        self.log("Saving songs...")

        for song in songs:
            try:
                song.write()
            except Exception as e:
                raise CommandError(e)

    def _execute(self, options, args):
        """Override to execute something"""

        raise NotImplemented

    def print_help(self, file=None):
        """Print the help information about the comand"""

        if file is None:
            file = sys.stdout

        self.__parser.print_help(file=file)

    def execute(self, args):
        """Execute the command"""

        options, args = self.__parser.parse_args(args)
        self._execute(options, args)
