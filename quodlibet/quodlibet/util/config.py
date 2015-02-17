# -*- coding: utf-8 -*-
# Copyright 2004-2008 Joe Wreschnig
#           2009-2013 Nick Boultbee
#           2011-2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

"""Simple proxy to a Python ConfigParser."""

import os
from StringIO import StringIO
import csv

# We don't need/want variable interpolation.
from ConfigParser import RawConfigParser as ConfigParser, Error

from quodlibet.util import atomic_save
from quodlibet.util.string import join_escape, split_escape
from quodlibet.util.path import is_fsnative, mkdir


# In newer RawConfigParser it is possible to replace the internal dict. The
# implementation only uses items() for writing, so replace with a dict that
# returns them sorted. This makes it easier to look up entries in the file.
class _sorted_dict(dict):
    def items(self):
        return sorted(super(_sorted_dict, self).items())


_DEFAULT = object()


class Config(object):
    """A wrapper around RawConfigParser"""

    def __init__(self, version=None):
        """Use read() to read in an existing config file.

        version should be an int starting with 0 that gets incremented if you
        want to register a new upgrade function. If None, upgrade is disabled.
        """

        self._config = ConfigParser(dict_type=_sorted_dict)
        self._version = version
        self._loaded_version = None
        self._upgrade_funcs = []
        self._initial = {}

    def _do_upgrade(self, func):
        assert self._loaded_version is not None
        assert self._version is not None

        old_version = self._loaded_version
        new_version = self._version
        if old_version != new_version:
            print_d("Config upgrade: %d->%d (%r)" % (
                old_version, new_version, func))
            func(self, old_version, new_version)

    def get_version(self):
        """Get the version of the loaded config file (for testing only)

        Raises Error if no file was loaded or versioning is disabled.
        """

        if self._version is None:
            raise Error("Versioning disabled")

        if self._loaded_version is None:
            raise Error("No file loaded")

        return self._loaded_version

    def register_upgrade_function(self, function):
        """Register an upgrade function that gets called at each read()
        if the current config version and the loaded version don't match.

        Can also be registered after read was called.

        function(config, old_version: int, new_version: int) -> None
        """

        if self._version is None:
            raise Error("Versioning disabled")

        self._upgrade_funcs.append(function)
        # after read(), so upgrade now
        if self._loaded_version is not None:
            self._do_upgrade(function)
        return function

    def set_inital(self, section, option, value):
        """Set an initial value for an option.

        The section must be added with add_section() first.

        Adds the value to the config and calling reset()
        will reset the value to it.
        """

        self.set(section, option, value)

        self._initial.setdefault(section, {})
        self._initial[section].setdefault(option, {})
        self._initial[section][option] = value

    def reset(self, section, option):
        """Reset the value to the initial state"""

        value = self._initial[section][option]
        self.set(section, option, value)

    def options(self, section):
        """Returns a list of options available in the specified section."""

        return self._config.options(section)

    def get(self, section, option, default=_DEFAULT):
        """get(section, option[, default]) -> str

        If default is not given, raises Error in case of an error
        """

        try:
            return self._config.get(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            return default

    def getboolean(self, section, option, default=_DEFAULT):
        """getboolean(section, option[, default]) -> bool

        If default is not given, raises Error in case of an error
        """

        try:
            return self._config.getboolean(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            if not isinstance(default, bool):
                raise ValueError
            return default

    def getint(self, section, option, default=_DEFAULT):
        """getint(section, option[, default]) -> int

        If default is not give, raises Error in case of an error
        """

        try:
            return self._config.getint(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            if not isinstance(default, int):
                raise ValueError
            return default

    def getfloat(self, section, option, default=_DEFAULT):
        """getfloat(section, option[, default]) -> float

        If default is not give, raises Error in case of an error
        """

        try:
            return self._config.getfloat(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            if not isinstance(default, float):
                raise ValueError
            return default

    def getstringlist(self, section, option, default=_DEFAULT):
        """getstringlist(section, option[, default]) -> list

        If default is not given, raises Error in case of an error.
        Gets a list of strings, using CSV to parse and delimit.
        """

        try:
            value = self._config.get(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            if not isinstance(default, list):
                raise ValueError
            return default

        parser = csv.reader(
            [value], lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
        try:
            vals = [v.decode('utf-8') for v in parser.next()]
        except (csv.Error, ValueError) as e:
            raise Error(e)

        return vals

    def setstringlist(self, section, option, values):
        """Saves a list of unicode strings using the csv module"""

        sw = StringIO()
        values = [unicode(v).encode('utf-8') for v in values]
        writer = csv.writer(sw, lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(values)
        self._config.set(section, option, sw.getvalue())

    def setlist(self, section, option, values, sep=","):
        """Saves a list of str using ',' as a separator and \\ for escaping"""

        values = map(str, values)
        joined = join_escape(values, sep)
        self._config.set(section, option, joined)

    def getlist(self, section, option, default=_DEFAULT, sep=","):
        """Returns a str list saved with setlist()"""

        try:
            value = self._config.get(section, option)
        except Error:
            if default is _DEFAULT:
                raise
            if not isinstance(default, list):
                raise ValueError
            return default

        return split_escape(value, sep)

    def set(self, section, option, value):
        """Saves the string representation for the passed value

        Don't pass unicode, encode first.
        """

        # RawConfigParser only allows string values but doesn't
        # scream if they are not (and it only fails before the
        # first config save..)
        if not isinstance(value, str):
            value = str(value)
        self._config.set(section, option, value)

    def setdefault(self, section, option, default):
        """Like set but only sets the new value if the option
        isn't set before.
        """

        if not self._config.has_option(section, option):
            self._config.set(section, option, default)

    def write(self, filename):
        """Write config to filename.

        Can raise EnvironmentError
        """

        assert is_fsnative(filename)

        mkdir(os.path.dirname(filename))

        # temporary set the new version for saving
        if self._version is not None:
            self.add_section("__config__")
            self.set("__config__", "version", self._version)
        try:
            with atomic_save(filename, ".tmp", "wb") as fileobj:
                self._config.write(fileobj)
        finally:
            if self._loaded_version is not None:
                self.set("__config__", "version", self._loaded_version)

    def clear(self):
        """Remove all sections and initial values"""

        for section in self._config.sections():
            self._config.remove_section(section)
        self._initial.clear()

    def is_empty(self):
        """Whether the config has any sections"""

        return not self._config.sections()

    def read(self, filename):
        """Reads the config from `filename` if the file exists,
        otherwise does nothing

        Can raise EnvironmentError, Error.
        """

        parsed_filenames = self._config.read(filename)

        # don't upgrade if we just created a new config
        if parsed_filenames and self._version is not None:
            self._loaded_version = self.getint("__config__", "version", -1)
            for func in self._upgrade_funcs:
                self._do_upgrade(func)

    def sections(self):
        """Return a list of the sections available"""

        return self._config.sections()

    def has_option(self, section, option):
        """If the given section exists, and contains the given option"""

        return self._config.has_option(section, option)

    def remove_option(self, section, option):
        """Remove the specified option from the specified section

        Can raise Error.
        """

        return self._config.remove_option(section, option)

    def add_section(self, section):
        """Add a section named section to the instance if it not already
        exists."""

        if not self._config.has_section(section):
            self._config.add_section(section)
