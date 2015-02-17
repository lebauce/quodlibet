# -*- coding: utf-8 -*-
# Copyright 2006 Joe Wreschnig
#           2012 Nick Boultbee
#           2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
"""
Librarians for libraries.
"""

import itertools

from gi.repository import GObject

from quodlibet.util.dprint import print_d


class Librarian(GObject.GObject):
    """The librarian is a nice interface to all active libraries.

    Librarians are a kind of meta-library. When any of their
    registered libraries fire a signal, they fire the same
    signal. Likewise, they provide various methods equivalent to the
    ones found in libraries that group the results of the real
    libraries.

    Attributes:
    libraries -- a dict mapping library names to libraries
    """

    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'removed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'added': (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self):
        super(Librarian, self).__init__()
        self.libraries = {}
        self.__signals = {}

    def destroy(self):
        pass

    def register(self, library, name):
        """Register a library with this librarian."""
        if name in self.libraries or name in self.__signals:
            raise ValueError("library %r is already active" % name)

        added_sig = library.connect('added', self.__added)
        removed_sig = library.connect('removed', self.__removed)
        changed_sig = library.connect('changed', self.__changed)
        self.libraries[name] = library
        self.__signals[library] = [added_sig, removed_sig, changed_sig]

    def _unregister(self, library, name):
        # This function, unlike register, should be private.
        # Libraries get unregistered at the discretion of the
        # librarian, not the libraries.
        del(self.libraries[name])
        for signal_id in self.__signals[library]:
            library.disconnect(signal_id)
        del(self.__signals[library])

    # FIXME: We can be smarter about this -- queue a list of items
    # and fire the signal after a short wait, to take advantage of
    # a case where many libraries fire a signal at the same time (or
    # one fires a signal often).

    def __changed(self, library, items):
        self.emit('changed', items)

    def __added(self, library, items):
        self.emit('added', items)

    def __removed(self, library, items):
        self.emit('removed', items)

    def changed(self, items):
        """Triage the items and inform their real libraries."""

        for library in self.libraries.itervalues():
            in_library = set(item for item in items if item in library)
            if in_library:
                library._changed(in_library)

    def __getitem__(self, key):
        """Find a item given its key."""
        for library in self.libraries.itervalues():
            try:
                return library[key]
            except KeyError:
                pass
        else:
            raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def remove(self, items):
        """Remove items from all libraries."""
        for library in self.libraries.itervalues():
            library.remove(items)

    def __contains__(self, item):
        """Check if a key or item is in the library."""
        for library in self.libraries.itervalues():
            if item in library:
                return True
        else:
            return False

    def __iter__(self):
        """Iterate over all items in all libraries."""
        return itertools.chain(*self.libraries.itervalues())

    def move(self, items, from_, to):
        """Move items from one library to another.

        This causes 'removed' signals on the from library, and 'added'
        signals on the 'to' library, but will not cause any signals
        to be emitted via this librarian.
        """
        try:
            from_.handler_block(self.__signals[from_][1])
            to.handler_block(self.__signals[to][0])
            from_.remove(items)
            to.add(items)
        finally:
            from_.handler_unblock(self.__signals[from_][1])
            to.handler_unblock(self.__signals[to][0])


class SongLibrarian(Librarian):
    """A librarian for SongLibraries."""

    def tag_values(self, tag):
        """Return a list of all values for the given tag."""
        tags = set()
        for library in self.libraries.itervalues():
            tags.update(library.tag_values(tag))
        return list(tags)

    def rename(self, song, newname, changed=None):
        """Rename the song in all libraries it belongs to.

        The 'changed' signal will fire for any library the song is in
        except if a set() is passed as changed.
        """
        # This needs to poke around inside the library directly.  If
        # it uses add/remove to handle the songs it fires incorrect
        # signals. If it uses the library's rename method, it breaks
        # the call for future libraries because the item's key has
        # changed. So, it needs to reimplement the method.
        re_add = []
        print_d("Renaming %r to %r" % (song.key, newname), self)
        for library in self.libraries.itervalues():
            try:
                del library._contents[song.key]
            except KeyError:
                pass
            else:
                re_add.append(library)
        song.rename(newname)
        for library in re_add:
            library._contents[song.key] = song
            if changed is None:
                library._changed(set([song]))
            else:
                print_d("Delaying changed signal for %r." % library, self)
                changed.add(song)

    def reload(self, item, changed=None, removed=None):
        """Reload a song (for all libraries), possibly noting its status.

        If sets are given, it assumes the caller will handle signals,
        and only updates the sets. Otherwise, it handles signals
        itself. It *always* handles library contents, so do not
        try to remove (again) a song that appears in the removed set.
        """

        had_item = []
        print_d("Reloading %r" % item.key, self)
        for library in self.libraries.itervalues():
            try:
                del library._contents[item.key]
            except KeyError:
                pass
            else:
                had_item.append(library)
        try:
            library = had_item[0]
        except IndexError:
            return

        # Rely on the first library in the list to do the actual
        # load, then just inform the other libraries what happened.
        was_changed, was_removed = library._load_item(item, force=True)
        assert not (was_changed and was_removed)

        if was_removed:
            if removed is None:
                for library in had_item:
                    library.emit('removed', set([item]))
            else:
                removed.add(item)
        elif was_changed:
            for library in had_item:
                library._contents[item.key] = item

            if changed is None:
                for library in had_item:
                    library.emit('changed', set([item]))
            else:
                changed.add(item)
