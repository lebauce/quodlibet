# -*- coding: utf-8 -*-
# Copyright 2004-2009 Joe Wreschnig, Michael Urman, Steven Robertson
#           2011-2013 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import re
import sys
import errno
import tempfile
import codecs
import shlex
import urllib
from quodlibet.const import FSCODING
from quodlibet.util.string import decode
from quodlibet import windows

if sys.platform == "darwin":
    from Foundation import NSString


"""
Path related functions like open, os.listdir have different behavior on win32

- Passing a string calls the old non unicode win API.
  In case of listdir this leads to "?" for >1byte chars and to
  1 byte chars encoded using the fs encoding. -> DO NOT USE!

- Passing a unicode object internally calls the windows unicode functions.
  This will mostly lead to proper unicode paths (except expanduser).

  And that's why QL is using unicode paths on win and encoded paths
  everywhere else.
"""


def mkdir(dir_, *args):
    """Make a directory, including all its parent directories. This does not
    raise an exception if the directory already exists (and is a
    directory)."""

    try:
        os.makedirs(dir_, *args)
    except OSError as e:
        if e.errno != errno.EEXIST or not os.path.isdir(dir_):
            raise


def fsdecode(s, note=True):
    """Takes a native path and returns unicode for displaying it.

    Can not fail and can't be reversed.
    """

    if isinstance(s, unicode):
        return s
    elif note:
        return decode(s, FSCODING)
    else:
        return s.decode(FSCODING, 'replace')


"""
There exist 3 types of paths:

 * Python: bytes on Linux, unicode on Windows
 * GLib: bytes on Linux, utf-8 bytes on Windows
 * Serialized for the config: same as GLib
"""


if sys.platform == "win32":
    # We use FSCODING to save paths in files for example,
    # so this should never change on Windows (like in glib)
    assert FSCODING == "utf-8"

    def is_fsnative(path):
        """If path is a native path"""

        return isinstance(path, unicode)

    def fsnative(path):
        """unicode -> native path"""

        assert isinstance(path, unicode)
        return path

    def glib2fsnative(path):
        """glib path -> native path"""

        assert isinstance(path, bytes)
        return path.decode("utf-8")

    def fsnative2glib(path):
        """native path -> glib path"""

        assert isinstance(path, unicode)
        return path.encode("utf-8")

    fsnative2bytes = fsnative2glib
    """native path -> bytes

    Can never fail.
    """

    bytes2fsnative = glib2fsnative
    """bytes -> native path

    Warning: This can fail (raise ValueError) only on Windows,
    if the input wasn't produced by fsnative2bytes.
    """
else:
    def is_fsnative(path):
        return isinstance(path, bytes)

    def fsnative(path):
        assert isinstance(path, unicode)
        return path.encode(FSCODING, 'replace')

    def glib2fsnative(path):
        assert isinstance(path, bytes)
        return path

    def fsnative2glib(path):
        assert isinstance(path, bytes)
        return path

    fsnative2bytes = fsnative2glib

    bytes2fsnative = glib2fsnative


def iscommand(s):
    """True if an executable file `s` exists in the user's path, or is a
    fully qualified and existing executable file."""

    if s == "" or os.path.sep in s:
        return os.path.isfile(s) and os.access(s, os.X_OK)
    else:
        s = s.split()[0]
        path = os.environ.get('PATH', '') or os.defpath
        for p in path.split(os.path.pathsep):
            p2 = os.path.join(p, s)
            if os.path.isfile(p2) and os.access(p2, os.X_OK):
                return True
        else:
            return False


def listdir(path, hidden=False):
    """List files in a directory, sorted, fully-qualified.

    If hidden is false, Unix-style hidden files are not returned.
    """

    assert is_fsnative(path)

    if hidden:
        filt = None
    else:
        filt = lambda base: not base.startswith(".")
    if path.endswith(os.sep):
        join = "".join
    else:
        join = os.sep.join
    return [join([path, basename])
            for basename in sorted(os.listdir(path))
            if filt(basename)]


if os.name == "nt":
    getcwd = os.getcwdu
    sep = os.sep.decode("ascii")
    pathsep = os.pathsep.decode("ascii")
else:
    getcwd = os.getcwd
    sep = os.sep
    pathsep = os.pathsep


def mtime(filename):
    """Return the mtime of a file, or 0 if an error occurs."""
    try:
        return os.path.getmtime(filename)
    except OSError:
        return 0


def filesize(filename):
    """Return the size of a file, or 0 if an error occurs."""
    try:
        return os.path.getsize(filename)
    except OSError:
        return 0


def escape_filename(s):
    """Escape a string in a manner suitable for a filename.

    Takes unicode or str and returns a fsnative path.
    """

    if isinstance(s, unicode):
        s = s.encode("utf-8")

    return fsnative(urllib.quote(s, safe="").decode("utf-8"))


def unescape_filename(s):
    """Unescape a string in a manner suitable for a filename."""
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    return urllib.unquote(s).decode("utf-8")


def expanduser(filename):
    """needed because expanduser does not return wide character paths
    on windows even if a unicode path gets passed.
    """

    if os.name == "nt":
        profile = windows.get_profile_dir() or u""
        if filename == "~":
            return profile
        if filename.startswith(u"~" + os.path.sep):
            return os.path.join(profile, filename[2:])
    return os.path.expanduser(filename)


def unexpand(filename, HOME=expanduser("~")):
    """Replace the user's home directory with ~/, if it appears at the
    start of the path name."""
    sub = (os.name == "nt" and "%USERPROFILE%") or "~"
    if filename == HOME:
        return sub
    elif filename.startswith(HOME + os.path.sep):
        filename = filename.replace(HOME, sub, 1)
    return filename


def find_mount_point(path):
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def pathname2url_win32(path):
    # stdlib version raises IOError for more than one ':' which can appear
    # using a virtual box shared folder and it inserts /// at the beginning
    # but it should be /.

    # windows paths should be unicode
    if isinstance(path, unicode):
        path = path.encode("utf-8")

    quote = urllib.quote
    if ":" not in path:
        return quote("/".join(path.split("\\")))
    drive, remain = path.split(":", 1)
    return "/%s:%s" % (quote(drive), quote("/".join(remain.split("\\"))))

if os.name == "nt":
    pathname2url = pathname2url_win32
else:
    pathname2url = urllib.pathname2url


def xdg_get_system_data_dirs():
    """http://standards.freedesktop.org/basedir-spec/latest/"""

    if os.name == "nt":
        from gi.repository import GLib
        dirs = []
        for dir_ in GLib.get_system_data_dirs():
            dirs.append(glib2fsnative(dir_))
        return dirs

    data_dirs = os.getenv("XDG_DATA_DIRS")
    if data_dirs:
        return map(os.path.abspath, data_dirs.split(":"))
    else:
        return ("/usr/local/share/", "/usr/share/")


def xdg_get_cache_home():
    if os.name == "nt":
        from gi.repository import GLib
        return glib2fsnative(GLib.get_user_cache_dir())

    data_home = os.getenv("XDG_CACHE_HOME")
    if data_home:
        return os.path.abspath(data_home)
    else:
        return os.path.join(os.path.expanduser("~"), ".cache")


def xdg_get_data_home():
    if os.name == "nt":
        from gi.repository import GLib
        return glib2fsnative(GLib.get_user_data_dir())

    data_home = os.getenv("XDG_DATA_HOME")
    if data_home:
        return os.path.abspath(data_home)
    else:
        return os.path.join(os.path.expanduser("~"), ".local", "share")


def xdg_get_config_home():
    if os.name == "nt":
        from gi.repository import GLib
        return glib2fsnative(GLib.get_user_config_dir())

    data_home = os.getenv("XDG_CONFIG_HOME")
    if data_home:
        return os.path.abspath(data_home)
    else:
        return os.path.join(os.path.expanduser("~"), ".config")


def parse_xdg_user_dirs(data):
    """Parses xdg-user-dirs and returns a dict of keys and paths.

    The paths depend on the content of os.environ while calling this function.
    See http://www.freedesktop.org/wiki/Software/xdg-user-dirs/

    Can't fail (but might return garbage).
    """
    paths = {}

    for line in data.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("=", 1)
        if len(parts) <= 1:
            continue
        key = parts[0]
        try:
            values = shlex.split(parts[1])
        except ValueError:
            continue
        if len(values) != 1:
            continue
        paths[key] = os.path.normpath(
            os.path.expandvars(bytes2fsnative(values[0])))

    return paths


def xdg_get_user_dirs():
    """Returns a dict of xdg keys to paths. The paths don't have to exist."""
    config_home = xdg_get_config_home()
    try:
        with open(os.path.join(config_home, "user-dirs.dirs"), "rb") as h:
            return parse_xdg_user_dirs(h.read())
    except EnvironmentError:
        return {}


def get_temp_cover_file(data):
    """Returns a file object or None"""

    try:
        # pass fsnative so that mkstemp() uses unicode on Windows
        fn = tempfile.NamedTemporaryFile(prefix=fsnative(u"tmp"))
        fn.write(data)
        fn.flush()
        fn.seek(0, 0)
    except EnvironmentError:
        return
    else:
        return fn


def _strip_win32_incompat(string, BAD='\:*?;"<>|'):
    """Strip Win32-incompatible characters from a Windows or Unix path."""

    if os.name == "nt":
        BAD += "/"

    if not string:
        return string

    new = "".join(map(lambda s: (s in BAD and "_") or s, string))
    parts = new.split(os.sep)

    def fix_end(string):
        return re.sub(r'[\. ]$', "_", string)
    return os.sep.join(map(fix_end, parts))


def strip_win32_incompat_from_path(string):
    """Strip Win32-incompatible chars from a path, ignoring os.sep
    and the drive part"""

    drive, tail = os.path.splitdrive(string)
    tail = os.sep.join(map(_strip_win32_incompat, tail.split(os.sep)))
    return drive + tail


def _normalize_darwin_path(filename, canonicalise=False):

    if canonicalise:
        filename = os.path.realpath(filename)
    filename = os.path.normpath(filename)

    decoded = filename.decode("utf-8", "quodlibet-osx-path-decode")

    try:
        return NSString.fileSystemRepresentation(decoded)
    except ValueError:
        return filename


def _normalize_path(filename, canonicalise=False):
    """Normalize a path on Windows / Linux
    If `canonicalise` is True, dereference symlinks etc
    by calling `os.path.realpath`
    """
    if canonicalise:
        filename = os.path.realpath(filename)
    filename = os.path.normpath(filename)
    return os.path.normcase(filename)


if sys.platform == "darwin":

    def _osx_path_decode_error_handler(error):
        bytes_ = bytearray(error.object[error.start:error.end])
        return (u"".join(map("%%%X".__mod__, bytes_)), error.end)

    codecs.register_error(
        "quodlibet-osx-path-decode", _osx_path_decode_error_handler)

    normalize_path = _normalize_darwin_path
else:
    normalize_path = _normalize_path


def path_equal(p1, p2, canonicalise=False):
    return normalize_path(p1, canonicalise) == normalize_path(p2, canonicalise)
