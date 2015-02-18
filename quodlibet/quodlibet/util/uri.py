# -*- coding: utf-8 -*-
# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

# TODO:
#  * netloc separation (user/passwd/host/port using urllib)
#  * Coerce a URI to Unicode (via an encoding for the path and
#    Punycode for the domain) and back.

import os
from urllib import url2pathname, quote_plus, unquote_plus
from urlparse import urlparse, urlunparse

from quodlibet.util.path import fsdecode, pathname2url


def _urlunparse(parts):
    # urlunparse doesn't like paths starting with // and will remove them.
    # we need them for UNC paths on Windows
    # e.g. we want "//foo/bar" -> urlparse -> urlunparse -> "//foo/bar"
    parts = list(parts)
    if parts[2].startswith("//") and not parts[1]:
        parts[2] = "//" + parts[2]
    return urlunparse(parts)


class URI(str):
    """A full URI string. This object provides several convenience
    attributes to access data from the urlparse and urllib modules.

    URIs inherit from str, and so any method that works on a str
    works on a URI.

    URIs are not closed under concatenation, slicing, and so on. Neither
    are these URI objects; such operations will return strs."""

    def __new__(klass, value, escaped=True):
        """Create a new URI object. By default, the URI is assumed to be
        escaped already. Pass escaped=False if you need the URI escaped
        (this is imperfect now).

        The URI returned will be equivalent, but not necessarily
        equal, to the value passed in."""

        values = list(urlparse(value))
        if not escaped:
            # FIXME: Handle netloc
            # FIXME: Handle query args
            values[2] = quote_plus(values[2], safe="/~")

        value = _urlunparse(values)
        obj = str.__new__(klass, value)

        # len() > 1 to not interpret windows paths as URIs
        # there are no schemes
        if not obj.scheme or not len(obj.scheme) > 1:
            raise ValueError("URIs must have a scheme, such as 'http://'")
        elif not (obj.netloc or obj.path):
            raise ValueError("URIs must have a network location or path")
        else:
            return obj

    @classmethod
    def frompath(klass, value):
        """Construct a URI from an unescaped filename."""

        return klass("file://" + pathname2url(value), escaped=True)

    @property
    def scheme(self):
        """URI scheme (e.g. 'http')"""
        return urlparse(self)[0]

    @property
    def netloc(self):
        """URI network location (e.g. 'example.com:21')"""
        return urlparse(self)[1]

    @property
    def path(self):
        """URI path (e.g. '/~user')"""

        return urlparse(self)[2]

    @property
    def params(self):
        """URI parameters"""
        return urlparse(self)[3]

    @property
    def query(self):
        """URI query string (e.g. 'foo=bar&a=b')"""
        return urlparse(self)[4]

    @property
    def fragment(self):
        """URI fragment ('foo' in '#foo')"""
        return urlparse(self)[5]

    @property
    def unescaped(self):
        """an unescaped str (not URI) version of the URI"""
        values = list(urlparse(self))
        values[2] = unquote_plus(values[2])
        return _urlunparse(values)

    @property
    def filename(self):
        """a local filename equivalent to the URI"""
        if self.scheme != "file":
            raise ValueError("only the file scheme supports filenames")
        elif self.netloc:
            raise ValueError("only local files have filenames")
        else:
            if os.name == "nt":
                return fsdecode(url2pathname(self.path))
            else:
                return url2pathname(self.path)

    @property
    def is_filename(self):
        """True if the URI is a valid (not necessarily existing)
        local filename
        """
        return self.scheme == "file" and not self.netloc

    def __repr__(self):
        return "<%s %r>" % (type(self).__name__, self.unescaped)
