# -*- coding: utf-8 -*-
# Copyright 2004-2009 Joe Wreschnig, Michael Urman, Steven Robertson
#           2011,2013 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import random
import re
import ctypes
import ctypes.util
import sys
import traceback
import urlparse
import unicodedata
import threading
import subprocess
import webbrowser
import contextlib

# Windows doesn't have fcntl, just don't lock for now
try:
    import fcntl
    fcntl
except ImportError:
    fcntl = None

from quodlibet.util.path import iscommand, is_fsnative
from quodlibet.util.string.titlecase import title

from quodlibet.const import SUPPORT_EMAIL, COPYRIGHT
from quodlibet.util.dprint import print_d, print_


class InstanceTracker(object):
    """A mixin for GObjects to return a list of all alive objects
    of a given type. Note that it must be used with a GObject or
    something with a connect method and destroy signal."""
    __kinds = {}

    def _register_instance(self, klass=None):
        """Register this object to be returned in the active instance list."""
        if klass is None:
            klass = type(self)
        self.__kinds.setdefault(klass, []).append(self)
        self.connect('destroy', self.__kinds[klass].remove)

    @classmethod
    def instances(klass):
        return klass.__kinds.get(klass, [])


class OptionParser(object):
    def __init__(self, name, version, description=None, usage=None):
        self.__name = name
        self.__version = version
        self.__args = {}
        self.__translate_short = {}
        self.__translate_long = {}
        self.__help = {}
        self.__usage = usage
        self.__description = description
        self.add(
            "help", shorts="h", help=_("Display brief usage information"))
        self.add(
            "version", shorts="v", help=_("Display version and copyright"))
        self.add("debug", shorts="d")

    def add(self, canon, help=None, arg="", shorts="", longs=[]):
        self.__args[canon] = arg
        for s in shorts:
            self.__translate_short[s] = canon
        for l in longs:
            self.__translate_long[l] = canon
        if help:
            self.__help[canon] = help

    def __shorts(self):
        shorts = ""
        for short, canon in self.__translate_short.items():
            shorts += short + (self.__args[canon] and "=" or "")
        return shorts

    def __longs(self):
        longs = []
        for long, arg in self.__args.items():
            longs.append(long + (arg and "=" or ""))
        for long, canon in self.__translate_long.items():
            longs.append(long + (self.__args[canon] and "=" or ""))
        return longs

    def __format_help(self, opt, space):
        if opt in self.__help:
            help = self.__help[opt]
            if self.__args[opt]:
                opt = "%s=%s" % (opt, self.__args[opt])
            return "  --%s %s\n" % (opt.ljust(space), help)
        else:
            return ""

    def help(self):
        l = 0
        for k in self.__help.keys():
            l = max(l, len(k) + len(self.__args.get(k, "")) + 4)

        s = _("Usage: %(program)s %(usage)s") % {
            "program": sys.argv[0],
            "usage": self.__usage if self.__usage else _("[options]"),
        }
        s += "\n"
        if self.__description:
            s += "%s - %s\n" % (self.__name, self.__description)
        s += "\n"
        keys = sorted(self.__help.keys())
        try:
            keys.remove("help")
        except ValueError:
            pass
        try:
            keys.remove("version")
        except ValueError:
            pass
        for h in keys:
            s += self.__format_help(h, l)
        if keys:
            s += "\n"
        s += self.__format_help("help", l)
        s += self.__format_help("version", l)
        return s

    def set_help(self, newhelp):
        self.__help = newhelp

    def version(self):
        return ("""\
{title} {version}
<{email}>
{copyright}\
""").format(title=self.__name, version=self.__version, dates="2004-2012",
            email=SUPPORT_EMAIL, copyright=COPYRIGHT)

    def parse(self, args=None):
        if args is None:
            args = sys.argv[1:]
        from getopt import getopt, GetoptError
        try:
            opts, args = getopt(args, self.__shorts(), self.__longs())
        except GetoptError, s:
            s = str(s)
            text = []
            if "not recognized" in s:
                text.append(
                    _("Option %r not recognized.") % s.split()[1])
            elif "requires argument" in s:
                text.append(
                    _("Option %r requires an argument.") % s.split()[1])
            elif "unique prefix" in s:
                text.append(
                    _("%r is not a unique prefix.") % s.split()[1])
            if "help" in self.__args:
                text.append(_("Try %s --help.") % sys.argv[0])

            print_e("\n".join(text))
            raise SystemExit(True)
        else:
            transopts = {}
            for o, a in opts:
                if o.startswith("--"):
                    o = self.__translate_long.get(o[2:], o[2:])
                elif o.startswith("-"):
                    o = self.__translate_short.get(o[1:], o[1:])
                if o == "help":
                    print_(self.help())
                    raise SystemExit
                elif o == "version":
                    print_(self.version())
                    raise SystemExit
                elif o == "debug":
                    from quodlibet import const
                    const.DEBUG = True
                if self.__args[o]:
                    transopts[o] = a
                else:
                    transopts[o] = True

            return transopts, args


def escape(str):
    """Escape a string in a manner suitable for XML/Pango."""
    return str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unescape(str):
    """Unescape a string in a manner suitable for XML/Pango."""
    return str.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def bold(string):
    return "<b>%s</b>" % string


def monospace(string):
    return "<tt>%s</tt>" % string


def italic(string):
    return "<i>%s</i>" % string


def parse_time(timestr, err=(ValueError, re.error)):
    """Parse a time string in hh:mm:ss, mm:ss, or ss format."""
    if timestr[0:1] == "-":
        m = -1
        timestr = timestr[1:]
    else:
        m = 1
    try:
        return m * reduce(lambda s, a: s * 60 + int(a),
                          re.split(r":|\.", timestr), 0)
    except err:
        return 0


def validate_query_date(datestr):
    """Validates a user provided date that can be compared using date_key().

    Returns True id the date is valid.
    """

    parts = datestr.split("-")
    if len(parts) > 3:
        return False

    if len(parts) > 2:
        try:
            v = int(parts[2])
        except ValueError:
            return False
        else:
            if not 1 <= v <= 31:
                return False

    if len(parts) > 1:
        try:
            v = int(parts[1])
        except ValueError:
            return False
        else:
            if not 1 <= v <= 12:
                return False

    try:
        int(parts[0])
    except ValueError:
        return False

    return True


def date_key(datestr):
    """Parse a date format y-m-d and returns an undefined integer that
    can only be used to compare dates.

    In case the date string is invalid the returned value is undefined.
    """

    # this basically does "2001-02-03" -> 20010203

    default = [0, 1, 1]
    parts = datestr.split("-")
    parts += default[len(parts):]

    value = 0
    for d, p, m in zip(default, parts, (10000, 100, 1)):
        try:
            value += int(p) * m
        except ValueError:
            # so that "2003-01-" is equal to "2003-01" ..
            value += d * m
    return value


def parse_date(datestr):
    """Parses yyyy-mm-dd date format and returns unix time.

    Raises ValueError in case the input couldn't be parsed.
    """

    import time

    try:
        frmt = ["%Y", "%Y-%m", "%Y-%m-%d"][datestr.count("-")]
    except IndexError:
        raise ValueError

    return time.mktime(time.strptime(datestr, frmt))


def format_rating(value, blank=True):
    """Turn a number into a sequence of rating symbols."""

    from quodlibet import config

    prefs = config.RATINGS
    steps = prefs.number
    value = max(min(value, 1.0), 0)
    ons = int(round(steps * value))
    offs = (steps - ons) if blank else 0
    return prefs.full_symbol * ons + prefs.blank_symbol * offs


def format_size(size):
    """Turn an integer size value into something human-readable."""
    # TODO: Better i18n of this (eg use O/KO/MO/GO in French)
    if size >= 1024 ** 3:
        return "%.1f GB" % (float(size) / (1024 ** 3))
    elif size >= 1024 ** 2 * 100:
        return "%.0f MB" % (float(size) / (1024 ** 2))
    elif size >= 1024 ** 2 * 10:
        return "%.1f MB" % (float(size) / (1024 ** 2))
    elif size >= 1024 ** 2:
        return "%.2f MB" % (float(size) / (1024 ** 2))
    elif size >= 1024 * 10:
        return "%d KB" % int(size / 1024)
    elif size >= 1024:
        return "%.2f KB" % (float(size) / 1024)
    else:
        return "%d B" % size


def format_time(time):
    """Turn a time value in seconds into hh:mm:ss or mm:ss."""

    if time < 0:
        time = abs(time)
        prefix = "-"
    else:
        prefix = ""
    if time >= 3600:  # 1 hour
        # time, in hours:minutes:seconds
        return "%s%d:%02d:%02d" % (prefix, time // 3600,
                                   (time % 3600) // 60, time % 60)
    else:
        # time, in minutes:seconds
        return "%s%d:%02d" % (prefix, time // 60, time % 60)


def format_time_display(time):
    """Like format_time, but will use RATIO instead of a colon to separate"""

    return format_time(time).replace(":", u"\u2236")


def format_time_long(time, limit=2):
    """Turn a time value in seconds into x hours, x minutes, etc.

    `limit` limits the count of units used, so the result will be <= time.
    0 means no limit.
    """

    if time < 1:
        return _("No time information")

    cutoffs = [
        (60, lambda n: ngettext("%d second", "%d seconds", n)),
        (60, lambda n: ngettext("%d minute", "%d minutes", n)),
        (24, lambda n: ngettext("%d hour", "%d hours", n)),
        (365, lambda n: ngettext("%d day", "%d days", n)),
        (None, lambda n: ngettext("%d year", "%d years", n)),
    ]

    time_str = []
    for divisor, gettext_partial in cutoffs:
        if time < 1:
            break
        if divisor is None:
            time, unit = 0, time
        else:
            time, unit = divmod(time, divisor)
        if unit:
            time_str.append(gettext_partial(unit) % unit)
    time_str.reverse()

    if limit:
        time_str = time_str[:limit]

    return ", ".join(time_str)


def capitalize(str):
    """Capitalize a string, not affecting any character after the first."""
    return str[:1].upper() + str[1:]


def _split_numeric_sortkey(s, limit=10,
                           reg=re.compile(r"[0-9][0-9]*\.?[0-9]*").search,
                           join=u" ".join):
    """Separate numeric values from the string and convert to float, so
    it can be used for human sorting. Also removes all extra whitespace."""
    result = reg(s)
    if not result or not limit:
        return (join(s.split()),)
    else:
        start, end = result.span()
        return (
            join(s[:start].split()),
            float(result.group()),
            _split_numeric_sortkey(s[end:], limit - 1))


def human_sort_key(s, normalize=unicodedata.normalize):
    if not isinstance(s, unicode):
        s = s.decode("utf-8")
    s = normalize("NFD", s.lower())
    return s and _split_numeric_sortkey(s)


def website(site):
    """Open the given URL in the user's default browser"""

    if os.name == "nt" or sys.platform == "darwin":
        return webbrowser.open(site)

    # all commands here return immediately
    for prog in ["xdg-open", "gnome-open"]:
        if not iscommand(prog):
            continue

        status = subprocess.check_call([prog, site])
        if status == 0:
            return True

    # sensible-browser is a debian thing
    blocking_progs = ["sensible-browser"]
    blocking_progs.extend(os.environ.get("BROWSER", "").split(":"))

    for prog in blocking_progs:
        if not iscommand(prog):
            continue

        # replace %s with the url
        args = prog.split()
        for i, arg in enumerate(args):
            if arg == "%s":
                args[i] = site
                break
        else:
            args.append(site)

        # calling e.g. firefox blocks, so call async and hope for the best
        try:
            spawn(args)
        except RuntimeError:
            continue
        else:
            return True

    return False


def tag(name, cap=True):
    # Return a 'natural' version of the tag for human-readable bits.
    # Strips ~ and ~# from the start and runs it through a map (which
    # the user can configure).
    if not name:
        return _("Invalid tag")
    else:
        from quodlibet.util.tags import readable
        parts = map(readable, tagsplit(name))
        if cap:
            # Translators: If tag names, when capitalized, should not
            # be title-cased ("Looks Like This"), but rather only have
            # the first letter capitalized, translate this string as
            # something other than "titlecase?".
            if C_("check", "titlecase?") == "titlecase?":
                parts = map(title, parts)
            else:
                parts = map(capitalize, parts)
        return " / ".join(parts)


def tagsplit(tag):
    """Split a (potentially) tied tag into a list of atomic tags. Two ~~s
    make the next tag prefixed with a ~, so ~foo~~bar => [foo, ~bar]."""
    if "~" in tag[1:]:
        if tag.startswith("~") and not tag.startswith("~#"):
            tag = tag[1:]
        tags = []
        front = ""
        for part in tag.split("~"):
            if part:
                tags.append(front + part)
                front = ""
            else:
                front = "~"
        return tags
    else:
        return [tag]


def pattern(pat, cap=True, esc=False):
    """Return a 'natural' version of the pattern string for human-readable
    bits. Assumes all tags in the pattern are present."""
    from quodlibet.pattern import Pattern, XMLFromPattern

    class Fakesong(dict):
        cap = False

        def comma(self, key):
            return " - ".join(self.list(key))

        def list(self, key):
            return [tag(k, self.cap) for k in tagsplit(key)]
        list_seperate = list
        __call__ = comma

    fakesong = Fakesong({'filename': tag('filename', cap)})
    fakesong.cap = cap
    try:
        p = (esc and XMLFromPattern(pat)) or Pattern(pat)
    except ValueError:
        return _("Invalid pattern")

    return p.format(fakesong)


def spawn(argv, stdout=False):
    """Asynchronously run a program. argv[0] is the executable name, which
    must be fully qualified or in the path. If stdout is True, return
    a file object corresponding to the child's standard output; otherwise,
    return the child's process ID.

    argv must be strictly str objects to avoid encoding confusion.
    """

    from gi.repository import GLib

    types = map(type, argv)
    if not (min(types) == max(types) == str):
        raise TypeError("executables and arguments must be str objects")
    print_d("Running %r" % " ".join(argv))
    args = GLib.spawn_async(argv=argv, flags=GLib.SpawnFlags.SEARCH_PATH,
                            standard_output=stdout)

    if stdout:
        return os.fdopen(args[2])
    else:
        return args[0]


def fver(tup):
    return ".".join(map(str, tup))


def uri_is_valid(uri):
    return bool(urlparse.urlparse(uri)[0])


def make_case_insensitive(filename):
    return "".join(["[%s%s]" % (c.lower(), c.upper()) for c in filename])


def print_exc(limit=None, file=None):
    """A wrapper preventing crashes on broken pipes in print_exc."""
    if not file:
        file = sys.stderr
    print_(traceback.format_exc(limit=limit), output=file)


class DeferredSignal(object):
    """A wrapper for connecting functions to signals.

    Some signals may fire hundreds of times, but only require processing
    once per group. This class pushes the call to the mainloop at idle
    priority and prevents multiple calls from being inserted in the
    mainloop at a time, greatly improving responsiveness in some places.

    When the target function will finally be called the arguments passed
    are the last arguments passed to DeferredSignal.

    `priority` defaults to GLib.PRIORITY_DEFAULT

    If `owner` is given, it will not call the target after the owner is
    destroyed.

    Example usage:

    def func(widget, user_arg):
        pass
    widget.connect('signal', DeferredSignal(func, owner=widget), user_arg)
    """

    def __init__(self, func, timeout=None, owner=None, priority=None):
        """timeout in milliseconds"""

        self.func = func
        self.dirty = False
        self.args = None

        if owner:
            def destroy_cb(owner):
                self.abort()
            owner.connect("destroy", destroy_cb)

        from gi.repository import GLib

        if priority is None:
            priority = GLib.PRIORITY_DEFAULT

        if timeout is None:
            self.do_idle_add = lambda f: GLib.idle_add(f, priority=priority)
        else:
            self.do_idle_add = lambda f: GLib.timeout_add(
                timeout, f, priority=priority)

    @property
    def im_self(self):
        return self.func.im_self

    @property
    def __code__(self):
        return self.func.__code__

    @property
    def __closure__(self):
        return self.func.__closure__

    def abort(self):
        """Abort any queued up calls.

        Can still be reused afterwards.
        """

        if self.dirty:
            from gi.repository import GLib
            GLib.source_remove(self._id)
            self.dirty = False
            self.args = None

    def __call__(self, *args):
        self.args = args
        if not self.dirty:
            self.dirty = True
            self._id = self.do_idle_add(self._wrap)

    def _wrap(self):
        self.func(*self.args)
        self.dirty = False
        self.args = None
        return False


def connect_obj(this, detailed_signal, handler, that, *args, **kwargs):
    """A wrapper for connect() that has the same interface as connect_object().
    Used as a temp solution to get rid of connect_object() calls which may
    be changed to match the C version more closely in the future.

    https://git.gnome.org/browse/pygobject/commit/?id=86fb12b3e9b75

    While it's not clear if switching to weak references will break anything,
    we mainly used this for adjusting the callback signature. So using
    connect() behind the scenes will keep things working as they are now.
    """

    def wrap(this, *args):
        return handler(that, *args)

    return this.connect(detailed_signal, wrap, *args, **kwargs)


def _connect_destroy(sender, func, detailed_signal, handler, *args, **kwargs):
    """Connect a bound method to a foreign object signal and disconnect
    if the object the method is bound to emits destroy (Gtk.Widget subclass).

    Also works if the handler is a nested function in a method and
    references the method's bound object.

    This solves the problem that the sender holds a strong reference
    to the bound method and the bound to object doesn't get GCed.
    """

    if hasattr(handler, "im_self"):
        obj = handler.im_self
    else:
        # XXX: get the "self" var of the enclosing scope.
        # Used for nested functions which ref the object but aren't methods.
        # In case they don't ref "self" normal connect() should be used anyway.
        index = handler.__code__.co_freevars.index("self")
        obj = handler.__closure__[index].cell_contents

    assert obj is not sender

    handler_id = func(detailed_signal, handler, *args, **kwargs)

    def disconnect_cb(*args):
        sender.disconnect(handler_id)

    obj.connect('destroy', disconnect_cb)
    return handler_id


def connect_destroy(sender, *args, **kwargs):
    return _connect_destroy(sender, sender.connect, *args, **kwargs)


def connect_after_destroy(sender, *args, **kwargs):
    return _connect_destroy(sender, sender.connect_after, *args, **kwargs)


class cached_property(object):
    """A read-only @property that is only evaluated once."""

    def __init__(self, fget, doc=None):
        self.fget = fget
        self.__doc__ = doc or fget.__doc__
        self.__name__ = name = fget.__name__
        # these get name mangled, so caching wont work unless
        # we mangle too
        assert not (name.startswith("__") and not name.endswith("__")), \
            "can't cache a dunder method"

    def __get__(self, obj, cls):
        if obj is None:
            return self
        obj.__dict__[self.__name__] = result = self.fget(obj)
        return result


def sanitize_tags(tags, stream=False):
    """Returns a new sanitized tag dict. stream defines if the
    tags of a main/base song should be changed or of a stream song.
    e.g. title will be removed for the base song but not for the stream one.
    """

    san = {}
    for key, value in tags.iteritems():
        key = key.lower()
        key = {"location": "website"}.get(key, key)

        if isinstance(value, unicode):
            lower = value.lower().strip()

            if key == "channel-mode":
                if "stereo" in lower or "dual" in lower:
                    value = u"stereo"
            elif key == "audio-codec":
                if "mp3" in lower:
                    value = u"MP3"
                elif "aac" in lower or "advanced" in lower:
                    value = u"MPEG-4 AAC"
                elif "vorbis" in lower:
                    value = u"Ogg Vorbis"

            if lower in ("http://www.shoutcast.com", "http://localhost/",
                         "default genre", "none", "http://", "unnamed server",
                         "unspecified", "n/a"):
                continue

        if key == "duration":
            try:
                value = int(long(value) / 1000)
            except ValueError:
                pass
            else:
                if not stream:
                    continue
                key = "~#length"
        elif key == "bitrate":
            try:
                value = int(value) / 1000
            except ValueError:
                pass
            else:
                if not stream:
                    continue
                key = "~#bitrate"
        elif key == "nominal-bitrate":
            try:
                value = int(value) / 1000
            except ValueError:
                pass
            else:
                if stream:
                    continue
                key = "~#bitrate"

        if key in ("emphasis", "mode", "layer", "maximum-bitrate",
                   "minimum-bitrate", "has-crc", "homepage"):
            continue

        if not stream and key in ("title", "album", "artist", "date"):
            continue

        if isinstance(value, (int, long, float)):
            if not key.startswith("~#"):
                key = "~#" + key
            san[key] = value
        else:
            if key.startswith("~#"):
                key = key[2:]

            if not isinstance(value, unicode):
                continue

            value = value.strip()
            if key in san:
                if value not in san[key].split("\n"):
                    san[key] += "\n" + value
            else:
                san[key] = value

    return san


def build_filter_query(key, values):
    """Create a text query that matches a union of all values for a key

    build_filter_query("foo", ["x", "y"])
    => foo = |("x"c, "y"c)
    build_filter_query("~#foo", ["1"])
    => #(foo = 1)
    """

    if not values:
        return u""
    if key.startswith("~#"):
        nheader = key[2:]
        queries = ["#(%s = %s)" % (nheader, i) for i in values]
        if len(queries) > 1:
            return u"|(%s)" % ", ".join(queries)
        else:
            return queries[0]
    else:
        text = ", ".join(
            ["'%s'c" % v.replace("\\", "\\\\").replace("'", "\\'")
             for v in values])
        if len(values) == 1:
            return u"%s = %s" % (key, text)
        else:
            return u"%s = |(%s)" % (key, text)


def limit_songs(songs, max, weight_by_ratings=False):
    """Choose at most `max` songs from `songs`,
    optionally giving weighting to ~#rating"""

    if not max or len(songs) < max:
        return songs
    else:
        if weight_by_ratings:
            def choose(r1, r2):
                if r1 or r2:
                    return cmp(random.random(), r1 / (r1 + r2))
                else:
                    return random.randint(-1, 1)

            def rating(song):
                return song("~#rating")
            songs.sort(cmp=choose, key=rating)
        else:
            random.shuffle(songs)
        return songs[:max]


def gi_require_versions(name, versions):
    """Like gi.require_version, but will take a list of versions.

    Returns the required version or raises ValueError.
    """

    assert versions

    import gi

    for version in versions:
        try:
            gi.require_version(name, version)
        except ValueError as e:
            pass
        else:
            return version
    else:
        raise e


@contextlib.contextmanager
def atomic_save(filename, suffix, mode):
    """Try to replace the content of a file in the safest way possible.

    * filename+suffix will be created during the process.
    * On UNIX this operation is atomic, on Windows it is not.

    with atomic_save("config.cfg", ".tmp", "wb") as f:
        f.write(data)

    Can raise.
    """

    assert is_fsnative(filename)

    temp_filename = filename + suffix
    fileobj = open(temp_filename, "wb")
    try:
        if fcntl is not None:
            fcntl.flock(fileobj.fileno(), fcntl.LOCK_EX)

        yield fileobj

        fileobj.flush()
        os.fsync(fileobj.fileno())

        # No atomic rename on windows
        if os.name == "nt":
            fileobj.close()
            try:
                os.remove(filename)
            except EnvironmentError:
                pass

        os.rename(temp_filename, filename)
    finally:
        if fcntl is not None:
            fcntl.flock(fileobj.fileno(), fcntl.LOCK_UN)
        fileobj.close()


def load_library(names, shared=True):
    """Load a ctypes library with a range of names to try.

    Handles direct .so names and library names ["libgpod.so", "gpod"].

    If shared is True can return a shared instance.
    Raises OSError if not found.

    Returns (library, name)
    """

    if not names:
        raise ValueError

    if shared:
        load_func = lambda n: getattr(ctypes.cdll, n)
    else:
        load_func = ctypes.cdll.LoadLibrary

    errors = []
    for name in names:
        dlopen_name = name
        if ".so" not in name and ".dll" not in name:
            dlopen_name = ctypes.util.find_library(name) or name

        try:
            return load_func(dlopen_name), name
        except OSError as e:
            errors.append(str(e))

    raise OSError("\n".join(errors))


def is_main_thread():
    """If the calling thread is the main one"""

    return threading.current_thread().name == "MainThread"


class MainRunnerError(Exception):
    pass


class MainRunnerAbortedError(MainRunnerError):
    pass


class MainRunnerTimeoutError(MainRunnerError):
    pass


class MainRunner(object):
    """Schedule a function call in the main loop from a
    worker thread and wait for the result.

    Make sure to call abort() before the main loop gets destroyed, otherwise
    the worker thread may block forever in call().
    """

    def __init__(self):
        self._source_id = None
        self._call_id = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._return = None
        self._error = None
        self._aborted = False

    def _run(self, func, *args, **kwargs):
        try:
            self._return = func(*args, **kwargs)
        except Exception as e:
            self._error = MainRunnerError(e)

    def _idle_run(self, call_id, call_event, func, *args, **kwargs):
        call_event.set()
        with self._lock:
            # In case a timeout happened but this got still
            # scheduled, this could be called after call() returns;
            # Compare to the current call id and do nothing if it isn't ours
            if call_id is not self._call_id:
                return False
            try:
                self._run(func, *args, **kwargs)
            finally:
                self._source_id = None
                self._cond.notify()
                return False

    def abort(self):
        """After this call returns no function will be executed anymore
        and a currently blocking call will fail with MainRunnerAbortedError.

        Can be called multiple times and can not fail.
        call() will always fail after this was called.
        """

        from gi.repository import GLib

        with self._lock:
            if self._aborted:
                return
            if self._source_id is not None:
                GLib.source_remove(self._source_id)
                self._source_id = None
            self._aborted = True
            self._call_id = None
            self._error = MainRunnerAbortedError("aborted")
            self._cond.notify()

    def call(self, func, *args, **kwargs):
        """Runs the function in the main loop and blocks until
        it is finshed or abort() was called. In case this is called
        from the main loop the function gets executed immediately.

        The priority kwargs defines the event source priority and will
        not be passed to func.

        In case a timeout kwarg is given the call will raise
        MainRunnerTimeoutError in case the function hasn't been scheduled
        (doesn't mean returned) until that time. timeout is a float in seconds.

        Can raise MainRunnerError in case the function raises an exception.
        Raises MainRunnerAbortedError in case the runner was aborted.
        Raises MainRunnerTimeoutError in case the timeout was reached.
        """

        from gi.repository import GLib

        with self._lock:
            if self._aborted:
                raise self._error
            self._error = None
            # XXX: ideally this should be GLib.MainContext.default().is_owner()
            # but that's not available in older pygobject
            if is_main_thread():
                kwargs.pop("priority", None)
                self._run(func, *args, **kwargs)
            else:
                assert self._source_id is None
                assert self._call_id is None
                timeout = kwargs.pop("timeout", None)
                call_event = threading.Event()
                self._call_id = object()
                self._source_id = GLib.idle_add(
                    self._idle_run, self._call_id, call_event,
                    func, *args, **kwargs)
                # only wait for the result if we are sure it got scheduled
                if call_event.wait(timeout):
                    self._cond.wait()
                self._call_id = None
                if self._source_id is not None:
                    GLib.source_remove(self._source_id)
                    self._source_id = None
                    raise MainRunnerTimeoutError("timeout: %r" % timeout)
            if self._error is not None:
                raise self._error
            return self._return


def re_escape(string, BAD="/.^$*+-?{,\\[]|()<>#=!:"):
    """A re.escape which also works with unicode"""

    needs_escape = lambda c: (c in BAD and "\\" + c) or c
    return type(string)().join(map(needs_escape, string))


def enum(cls):
    """Class decorator for enum types::

        @enum
        class SomeEnum(object):
            FOO = 0
            BAR = 1

    Result is an int subclass and all attributes are instances of it.
    """

    assert cls.__bases__ == (object,)

    d = dict(cls.__dict__)
    new_type = type(cls.__name__, (int,), d)
    new_type.__module__ = cls.__module__

    map_ = {}
    for key, value in d.iteritems():
        if key.upper() == key and isinstance(value, (int, long)):
            value_instance = new_type(value)
            setattr(new_type, key, value_instance)
            map_[value] = key

    def repr_(self):
        if self in map_:
            return "%s.%s" % (type(self).__name__, map_[self])
        else:
            return "%s(%s)" % (type(self).__name__, self)

    setattr(new_type, "__repr__", repr_)

    return new_type


def set_process_title(title):
    """Sets process name as visible in ps or top. Requires ctypes libc
    and is almost certainly *nix-only. See issue 736
    """

    if os.name == "nt":
        return

    try:
        libc = load_library(["libc.so.6", "c"])[0]
        # 15 = PR_SET_NAME, apparently
        libc.prctl(15, title, 0, 0, 0)
    except (OSError, AttributeError):
        print_d("Couldn't find module libc.so.6 (ctypes). "
                "Not setting process title.")


def list_unique(sequence):
    """Takes any sequence and returns a list with all duplicate entries
    removed while preserving the order.
    """

    l = []
    seen = set()
    append = l.append
    add = seen.add
    for v in sequence:
        if v not in seen:
            append(v)
            add(v)
    return l


def set_win32_unicode_argv():
    if os.name != "nt":
        return

    import ctypes
    from ctypes import cdll, windll, wintypes

    GetCommandLineW = cdll.kernel32.GetCommandLineW
    GetCommandLineW.argtypes = []
    GetCommandLineW.restype = wintypes.LPCWSTR

    CommandLineToArgvW = windll.shell32.CommandLineToArgvW
    CommandLineToArgvW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

    LocalFree = windll.kernel32.LocalFree
    LocalFree.argtypes = [wintypes.HLOCAL]
    LocalFree.restype = wintypes.HLOCAL

    argc = ctypes.c_int()
    argv = CommandLineToArgvW(GetCommandLineW(), ctypes.byref(argc))
    if not argv:
        return

    sys.argv = argv[max(0, argc.value - len(sys.argv)):argc.value]

    LocalFree(argv)
