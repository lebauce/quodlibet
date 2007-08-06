# Copyright 2004-2005 Joe Wreschnig, Michael Urman
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#
# $Id$

import time

TIME_KEYS = ["added", "mtime", "lastplayed", "laststarted"]

# True if the object matches any of its REs.
class Union(object):
    def __init__(self, res):
        self.__res = res

    def search(self, data):
        for re in self.__res:
            if re.search(data): return True
        return False

    def __repr__(self):
        return "<Union %r>" % self.__res

# True if the object matches all of its REs.
class Inter(object):
    def __init__(self, res):
        self.__res = res

    def search(self, data):
        for re in self.__res:
            if not re.search(data): return False
        return True

    def __repr__(self):
        return "<Inter %r>" % self.__res

# True if the object doesn't match its RE.
class Neg(object):
    def __init__(self, re):
        self.__re = re

    def search(self, data):
        return not self.__re.search(data)

    def __repr__(self):
        return "<Neg %r>" % self.__re

# Numeric comparisons
class Numcmp(object):
    def __init__(self, tag, op, value):
        if isinstance(tag, unicode): self.__tag = tag.encode("utf-8")
        else: self.__tag = tag
        self.__ftag = "~#" + self.__tag
        self.__shortcircuit = tag.startswith("playlist")
        self.__op = op
        value = value.strip()

        if tag in TIME_KEYS:
            if self.__op == ">": self.__op = "<"
            elif self.__op == "<": self.__op = ">"
            elif self.__op == "<=": self.__op = ">="
            elif self.__op == ">=": self.__op = "<="

        if value in ["now"]: value = int(time.time())
        elif value in ["today"]: value = int(time.time() - 24 * 60 * 60)
        else:
            parts = value.split()
            try: value = round(float(parts[0]), 2)
            except ValueError:
                try:
                    hms = map(int, value.split(":"))
                    value = 0
                    for t in hms:
                        value *= 60
                        value += t
                except ValueError:
                    value = 0
            if len(parts) > 1:
                unit = parts[1].strip("s")
                if unit == "minute": value *= 60
                if unit == "hour": value *= 60 * 60
                elif unit == "day": value *= 24 * 60 * 60
                elif unit == "week": value *= 7 * 24 * 60 * 60
                elif unit == "year": value *= 365 * 24 * 60 * 60

                if tag in TIME_KEYS:
                    value = int(time.time() - value)
        self.__value = value

    def search(self, data):
        if self.__shortcircuit: num = data.get(self.__ftag, 0)
        else: num = data(self.__ftag, 0)
        num = round(num, 2)
        if   self.__op == ">":  return num >  self.__value
        elif self.__op == "<":  return num <  self.__value
        elif self.__op == "=":  return num == self.__value
        elif self.__op == ">=": return num >= self.__value
        elif self.__op == "<=": return num <= self.__value
        elif self.__op == "!=": return num != self.__value
        else: raise ValueError("Unknown operator %s" % self.__op)

    def __repr__(self):
        return "<Numcmp tag=%r, op=%r, value=%d>"%(
            self.__tag, self.__op, self.__value)

# See if a property of the object matches its RE.
class Tag(object):

    # Shorthand for common tags.
    ABBRS = { "a": "artist",
              "b": "album",
              "v": "version",
              "t": "title",
              "n": "tracknumber",
              "d": "date",
              }
    def __init__(self, names, res):
        self.__names = [Tag.ABBRS.get(n.lower(), n.lower()) for n in names]
        self.__res = res
        if not isinstance(self.__res, list): self.__res = [self.__res]
        if len([name for name in self.__names if name.startswith('~')]):
            self.search = self.__search_synth

    def __search_synth(self, data):
        for name in self.__names:
            for re in self.__res:
                if name.startswith('~'):
                    if re.search(data(name, "")):
                        return True
                elif re.search(data.get(name, data.get("~"+name, ""))):
                    return True
        return False

    def search(self, data):
        for name in self.__names:
            for re in self.__res:
                if re.search(data.get(name, data.get("~"+name, ""))):
                    return True
        return False

    def __repr__(self):
        return ("<Tag names=%r, res=%r>" % (self.__names, self.__res))
