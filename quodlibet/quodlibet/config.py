# Copyright 2004-2008 Joe Wreschnig
#           2009-2013 Nick Boultbee
#           2011-2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from StringIO import StringIO
import csv
import os
import shutil

import const
from quodlibet.util.config import Config, Error

# Some plugins can be enabled on first install
AUTO_ENABLED_PLUGINS = ["Shuffle Playlist", "Remove Playlist Duplicates"]

# this defines the initial and default values
INITIAL = {
    # User-defined tag name -> human name mappings
    "header_maps": {
    },
    "player": {
        "time_remaining": "false",
        "replaygain": "on",
        "fallback_gain": "0.0",
        "pre_amp_gain": "0.0",
        "backend": "gstbe",
        "gst_pipeline": "",
        "gst_buffer": "1.5", # stream buffer duration in seconds
        "gst_device": "",
        "gst_disable_gapless": "true",
    },
    "library": {
        "exclude": "",
        "refresh_on_start": "true",
    },
    # State about the player, to restore on startup
    "memory": {
        "song": "", # filename of last song
        "seek": "0", # last song position, in milliseconds
        "volume": "1.0", # internal volume, [0.0, 1.0]
        "browser": "PanedBrowser", # browser name
        "songlist": "true", # on or off
        "queue": "false", # on or off
        "shufflequeue": "false", # on or off
        "sortby": "0album", # <reversed?>tagname, song list sort
        "order": "inorder",
        "order_shuffle": "shuffle",
        "shuffle": "false",
        "plugin_selection": "", # selected plugin in manager
        "column_widths": "", # column widths in c1,w1,c2,w2... format
        "column_expands": "",
    },
    "browsers": {
        "query_text": "", # none/search bar text
        # panes in paned browser
        "panes":
            "~people	<~year|[b][i]<~year>[/i][/b] - ><album>",
        "pane_selection": "", # selected pane values
        "pane_wide_mode": "0", # browser orientation
        "background": "", # "global" filter for SearchBar
        "albums": "", # album list
        "album_sort": "0", # album sorting mode, default is title
        "album_covers": "1", # album cover display, on/off
        "album_substrings": "1", # include substrings in inline search
        "collection_headers": "~people 0",
        "radio": "", # radio filter selection
        "rating_click": "true", # click to rate song, on/off
        "rating_confirm_multiple": "false", # confirm rating multiple songs
        "cover_size": "-1", # max cover height/width, <= 0 is default
        "search_limit": "false", # Show the limit widgets for SearchBar
    },
    # Kind of a dumping ground right now, should probably be
    # cleaned out later.
    "settings": {
        # scan directories, :-separated
        "scan": "",

        # scroll song list on current song change
        "jump": "true",

        # Unrated songs are given this value
        "default_rating": "0.5",

        # Rating scale i.e. maximum number of symbols
        "ratings": "4",

        # (0 = disabled i.e. arithmetic mean)
        "bayesian_rating_factor": "0.0",

        # rating symbol (black star)
        "rating_symbol_full": "\xe2\x98\x85",

        # rating symbol (hollow star)
        "rating_symbol_blank": "\xe2\x98\x86",

        # probably belongs in memory
        "repeat": "false",

        # Now deprecated: space-separated headers column
        #"headers": " ".join(const.DEFAULT_COLUMNS),

        # 2.6: this gets migrated from headers entry in code.
        # TODO: re-instate columns here in > 2.6 or once most have migrated
        #"columns": ",".join(const.DEFAULT_COLUMNS),

        # hack to disable hints, see bug #526
        "disable_hints": "false",

        # search as soon as text is typed into search box
        "eager_search": "true",
    },
    "rename": {
        "spaces": "false",
        "windows": "true",
        "ascii": "false",
    },
    "tagsfrompath": {
        "underscores": "false",
        "titlecase": "false",
        "split": "false",
        "add": "false",
    },
    "plugins": {
        # newline-separated plugin IDs
        "active_plugins": "\n".join(AUTO_ENABLED_PLUGINS),
        # Issue 1231: Maximum number of SongsMenu plugins to run at once
        "default_max_plugin_invocations": 30,
    },
    "editing": {
        "split_on": "/ & ,", # words to split on
        "id3encoding": "", # ID3 encodings to try
        "human_title_case": "true",
        "save_to_songs": "true",
        "save_email": const.EMAIL,
        "alltags": "true", # show all tags, or just "human-readable" ones
        # Skip dialog to save or revert changes
        "auto_save_changes": "false"
    },
    "albumart": {
        "round": "true", # use rounded corners for artwork thumbnails
        "prefer_embedded": "false",
        "force_filename": "false",
        "filename": "folder.jpg",
    }
}


# global instance
_config = Config(version=0)

options = _config.options
get = _config.get
getboolean = _config.getboolean
getint = _config.getint
getfloat = _config.getfloat
getstringlist = _config.getstringlist
setstringlist = _config.setstringlist
set = _config.set
setdefault = _config.setdefault
write = _config.write
reset = _config.reset
add_section = _config.add_section
has_option = _config.has_option
remove_option = _config.remove_option
register_upgrade_function = _config.register_upgrade_function


def init(filename=None, initial=None):
    if not _config.is_empty():
        raise ValueError(
            "config initialized twice without quitting: %r"
            % _config.sections())

    if initial is None:
        initial = INITIAL

    for section, values in initial.iteritems():
        _config.add_section(section)
        for key, value in values.iteritems():
            _config.set_inital(section, key, value)

    if filename is not None:
        try:
            _config.read(filename)
        except (Error, EnvironmentError):
            print_w("Reading config file %r failed." % filename)

            # move the broken file out of the way
            try:
                shutil.copy(filename, filename + ".not-valid")
            except EnvironmentError:
                pass


def save(filename):
    """Writes the active config to filename, ignoring all possible errors"""

    print_d("Writing config...")
    try:
        _config.write(filename)
    except EnvironmentError:
        print_w("Unable to write config.")


def quit():
    """Clears the active config"""

    _config.clear()


def state(arg):
    return _config.getboolean("settings", arg)


def get_columns():
    """Gets the list of songlist column headings"""

    if has_option("settings", "columns"):
        return getstringlist("settings", "columns", const.DEFAULT_COLUMNS)
    else:
        # migrate old settings
        try:
            columns = get("settings", "headers").split()
        except Error:
            return const.DEFAULT_COLUMNS
        else:
            _config.remove_option("settings", "headers")
            set_columns(columns)
            setstringlist("settings", "columns", columns)
            return columns


def set_columns(vals):
    """Persists the settings for songlist headings held in `vals`"""

    setstringlist("settings", "columns", vals)


@register_upgrade_function
def _migrate_rating_column(config, old, new):
    if old < 0:
        columns = get_columns()[:]
        for i, c in enumerate(columns):
            if c == "~#rating":
                columns[i] = "~rating"
        set_columns(columns)


class RatingsPrefs(object):
    """
    Models Ratings settings as configured by the user, with caching.
    """
    def __init__(self):
        self.__number = self.__default = None
        self.__full_symbol = self.__blank_symbol = None

    @property
    def precision(self):
        """Returns the smallest ratings delta currently configured"""
        return 1.0 / self.number

    @property
    def number(self):
        if self.__number is None:
            self.__number = getint("settings", "ratings")
        return self.__number

    @number.setter
    def number(self, i):
        """The (maximum) integer number of ratings icons configured"""
        self.__number = self.__save("ratings", int(i))

    @property
    def default(self):
        """The current default floating-point rating"""
        if self.__default is None:
            self.__default = getfloat("settings", "default_rating")
        return self.__default

    @default.setter
    def default(self, f):
        self.__default = self.__save("default_rating", float(f))

    @property
    def full_symbol(self):
        """The symbol to use for a full (active) rating"""
        if self.__full_symbol is None:
            self.__full_symbol = self.__get_symbol("full")
        return self.__full_symbol

    @full_symbol.setter
    def full_symbol(self, s):
        self.__full_symbol = self.__save("rating_symbol_full", s)

    @property
    def blank_symbol(self):
        """The symbol to use for a blank (inactive) rating, if needed"""
        if self.__blank_symbol is None:
            self.__blank_symbol = self.__get_symbol("blank")
        return self.__blank_symbol

    @blank_symbol.setter
    def blank_symbol(self, s):
        self.__blank_symbol = self.__save("rating_symbol_blank", s)

    @property
    def all(self):
        """Returns all the possible ratings currently available"""
        return [float(i) / self.number for i in range(0, self.number + 1)]

    @staticmethod
    def __save(key, value):
        set("settings", key, value)
        return value

    @staticmethod
    def __get_symbol(variant="full"):
        return get("settings", "rating_symbol_%s" % variant).decode("utf-8")


class HardCodedRatingsPrefs(RatingsPrefs):
    number = int(INITIAL["settings"]["ratings"])
    default = float(INITIAL["settings"]["default_rating"])
    blank_symbol = INITIAL["settings"]["rating_symbol_blank"].decode("utf-8")
    full_symbol = INITIAL["settings"]["rating_symbol_full"].decode("utf-8")

# Need an instance just for imports to work
RATINGS = RatingsPrefs()
