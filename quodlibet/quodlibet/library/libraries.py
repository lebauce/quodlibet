# Copyright 2006 Joe Wreschnig
#           2013,2014 Nick Boultbee
#           2013,2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

"""Base library classes.

These classes are the most basic library classes. As such they are the
least useful but most content-agnostic.
"""

import cPickle as pickle
import os
import shutil
import threading
import time

from gi.repository import GObject, Gio

from quodlibet.formats import MusicFile
from quodlibet.parse import Query
from quodlibet.qltk.notif import Task
from quodlibet import config
from quodlibet.util import copool
from quodlibet.util.library import get_scan_dirs, get_excluded_scan_dirs
from quodlibet.util.collection import Album
from quodlibet.util.collections import DictMixin
from quodlibet import util
from quodlibet import const
from quodlibet import formats
from quodlibet.util.dprint import print_d, print_w
from quodlibet.util.path import fsdecode, expanduser, unexpand, mkdir, \
    normalize_path, fsencode, is_fsnative


class Library(GObject.GObject, DictMixin):
    """A Library contains useful objects.

    The only required method these objects support is a .key
    attribute, but specific types of libraries may require more
    advanced interfaces.

    Every method which takes a sequence of items expects items to
    implement __iter__, __len__ and __contains__.

    Likewise the signals emit sequences which implement
    __iter__, __len__ and __contains__ e.g. set(), list() or tuple().

    WARNING: The library implements the dict interface with the exception
    that iterating over it yields values and not keys.
    """

    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'removed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'added': (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    librarian = None
    dirty = False

    def __init__(self, name=None):
        super(Library, self).__init__()
        self._contents = {}
        self._name = name
        if self.librarian is not None and name is not None:
            self.librarian.register(self, name)

    def destroy(self):
        if self.librarian is not None and self._name is not None:
            self.librarian._unregister(self, self._name)

    def changed(self, items):
        """Alert other users that these items have changed.

        This causes a 'changed' signal. If a librarian is available
        this function will call its changed method instead, and all
        libraries that librarian manages may fire a 'changed' signal.

        The item list may be filtered to those items actually in the
        library. If a librarian is available, it will handle the
        filtering instead. That means if this method is delegated to
        the librarian, this library's changed signal may not fire, but
        another's might.
        """

        if not items:
            return
        if self.librarian and self in self.librarian.libraries.itervalues():
            print_d("Changing %d items via librarian." % len(items), self)
            self.librarian.changed(items)
        else:
            items = set(item for item in items if item in self)
            if not items:
                return
            print_d("Changing %d items directly." % len(items), self)
            self._changed(items)

    def _changed(self, items):
        assert isinstance(items, set)

        # Called by the changed method and Librarians.
        if not items:
            return
        print_d("Changing %d items." % len(items), self)
        self.dirty = True
        self.emit('changed', items)

    def __iter__(self):
        """Iterate over the items in the library."""
        return self._contents.itervalues()

    def iteritems(self):
        return self._contents.iteritems()

    def iterkeys(self):
        return self._contents.iterkeys()

    def itervalues(self):
        return self._contents.itervalues()

    def __len__(self):
        """The number of items in the library."""
        return len(self._contents)

    def __getitem__(self, key):
        """Find a item given its key."""
        return self._contents[key]

    def __contains__(self, item):
        """Check if a key or item is in the library."""
        try:
            return item in self._contents or item.key in self._contents
        except AttributeError:
            return False

    def get_content(self):
        """All items including hidden ones for saving the library
           (see FileLibrary with masked items)"""
        return self.values()

    def keys(self):
        return self._contents.keys()

    def values(self):
        return self._contents.values()

    def _load_item(self, item):
        """Load (add) an item into this library"""
        # Subclasses should override this if they want to check
        # item validity; see `FileLibrary`.
        print_d("Loading %r." % item.key, self)
        self.dirty = True
        self._contents[item.key] = item

    def _load_init(self, items):
        """Load many items into the library (on start)"""
        # Subclasses should override this if they want to check
        # item validity; see `FileLibrary`.
        content = self._contents
        for item in items:
            content[item.key] = item

    def add(self, items):
        """Add items. This causes an 'added' signal.

        Return the sequence of items actually added, filtering out items
        already in the library.
        """

        items = set(item for item in items if item not in self)
        if not items:
            return items

        print_d("Adding %d items." % len(items), self)
        for item in items:
            self._contents[item.key] = item

        self.dirty = True
        self.emit('added', items)
        return items

    def remove(self, items):
        """Remove items. This causes a 'removed' signal.

        Return the sequence of items actually removed.
        """

        items = set(item for item in items if item in self)
        if not items:
            return items

        print_d("Removing %d items." % len(items), self)
        for item in items:
            del(self._contents[item.key])

        self.dirty = True
        self.emit('removed', items)
        return items


def dump_items(filename, items):
    """Pickle items to disk.

    Doesn't handle exceptions.
    """

    dirname = os.path.dirname(filename)
    mkdir(dirname)

    with util.atomic_save(filename, ".tmp", "wb") as fileobj:
        # While protocol 2 is usually faster it uses __setitem__
        # for unpickle and we override it to clear the sort cache.
        # This roundtrip makes it much slower, so we use protocol 1
        # unpickle numbers (py2.7):
        #   2: 0.66s / 2 + __set_item__: 1.18s / 1 + __set_item__: 0.72s
        # see: http://bugs.python.org/issue826897
        pickle.dump(items, fileobj, 1)


def load_items(filename, default=None):
    """Load items from disk.

    In case of an error returns default or an empty list.
    """

    if default is None:
        default = []

    try:
        fp = open(filename, "rb")
    except EnvironmentError:
        if const.DEBUG or os.path.exists(filename):
            print_w("Couldn't load library from: %r" % filename)
        return default

    # pickle makes 1000 read syscalls for 6000 songs
    # read the file into memory so that there are less
    # context switches. saves 40% CPU time..
    try:
        data = fp.read()
    except IOError:
        fp.close()
        return default

    try:
        items = pickle.loads(data)
    except Exception:
        # there are too many ways this could fail
        util.print_exc()

        # move the broken file out of the way
        try:
            shutil.copy(filename, filename + ".not-valid")
        except EnvironmentError:
            util.print_exc()

        items = default

    return items


class PicklingMixin(object):
    """A mixin to provide persistence of a library by pickling to disk"""

    filename = None

    def __init__(self):
        self._save_lock = threading.Lock()

    def load(self, filename):
        """Load a library from a file, containing a picked list.

        Loading does not cause added, changed, or removed signals.
        """

        self.filename = filename
        print_d("Loading contents of %r." % filename, self)

        items = load_items(filename)

        # this loads all items without checking their validity, but makes
        # sure that non-mounted items are masked
        self._load_init(items)

        print_d("Done loading contents of %r." % filename, self)

    def save(self, filename=None):
        """Save the library to the given filename, or the default if `None`"""

        if filename is None:
            filename = self.filename

        with self._save_lock:
            print_d("Saving contents to %r." % filename, self)

            try:
                dump_items(filename, self.get_content())
            except EnvironmentError:
                print_w("Couldn't save library to path: %r" % filename)
            else:
                self.dirty = False


class PicklingLibrary(Library, PicklingMixin):
    """A library that pickles its contents to disk"""
    def __init__(self, name=None):
        print_d("Using pickling persistence for library \"%s\"" % name)
        PicklingMixin.__init__(self)
        Library.__init__(self, name)


class AlbumLibrary(Library):
    """An AlbumLibrary listens to a SongLibrary and sorts its songs into
    albums.

    The library behaves like a dictionary: the keys are album_keys of
    AudioFiles, the values are Album objects.
    """

    def __init__(self, library):
        self.librarian = None
        print_d("Initializing Album Library to watch %r" % library._name)

        super(AlbumLibrary, self).__init__(
            "AlbumLibrary for %s" % library._name)

        self._library = library
        self._asig = library.connect('added', self.__added)
        self._rsig = library.connect('removed', self.__removed)
        self._csig = library.connect('changed', self.__changed)
        self.__added(library, library.values(), signal=False)

    def refresh(self, items):
        """Refresh albums after a manual change."""
        self._changed(set(items))

    def load(self):
        # deprecated
        pass

    def destroy(self):
        for sig in [self._asig, self._rsig, self._csig]:
            self._library.disconnect(sig)

    def _get(self, item):
        return self._contents.get(item)

    def __add(self, items):
        changed = set()
        new = set()
        for song in items:
            key = song.album_key
            if key in self._contents:
                changed.add(self._contents[key])
            else:
                album = Album(song)
                self._contents[key] = album
                new.add(album)
            self._contents[key].songs.add(song)

        changed -= new
        return changed, new

    def __added(self, library, items, signal=True):
        changed, new = self.__add(items)

        for album in changed:
            album.finalize()

        if signal:
            if new:
                self.emit('added', new)
            if changed:
                self.emit('changed', changed)

    def __removed(self, library, items):
        changed = set()
        removed = set()
        for song in items:
            key = song.album_key
            album = self._contents[key]
            album.songs.remove(song)
            changed.add(album)
            if not album.songs:
                removed.add(album)
                del self._contents[key]

        changed -= removed

        for album in changed:
            album.finalize()

        if removed:
            self.emit('removed', removed)
        if changed:
            self.emit('changed', changed)

    def __changed(self, library, items):
        """Album keys could change between already existing ones.. so we
        have to do it the hard way and search by id."""
        print_d("Updating affected albums for %d items" % len(items))
        changed = set()
        removed = set()
        to_add = []
        for song in items:
            # in case the key hasn't changed
            key = song.album_key
            if key in self._contents and song in self._contents[key].songs:
                changed.add(self._contents[key])
            else:  # key changed.. look for it in each album
                to_add.append(song)
                for key, album in self._contents.iteritems():
                    if song in album.songs:
                        album.songs.remove(song)
                        if not album.songs:
                            removed.add(album)
                        else:
                            changed.add(album)
                        break

        # get new albums and changed ones because keys could have changed
        add_changed, new = self.__add(to_add)
        changed |= add_changed

        # check if albums that were empty at some point are still empty
        for album in removed:
            if not album.songs:
                del self._contents[album.key]
                changed.discard(album)

        for album in changed:
            album.finalize()

        if removed:
            self.emit("removed", removed)
        if changed:
            self.emit("changed", changed)
        if new:
            self.emit("added", new)


class SongLibrary(PicklingLibrary):
    """A library for songs.

    Items in this kind of library must support (roughly) the AudioFile
    interface.
    """

    def __init__(self, *args, **kwargs):
        super(SongLibrary, self).__init__(*args, **kwargs)

    @util.cached_property
    def albums(self):
        return AlbumLibrary(self)

    def destroy(self):
        super(SongLibrary, self).destroy()
        if "albums" in self.__dict__:
            self.albums.destroy()

    def tag_values(self, tag):
        """Return a list of all values for the given tag."""
        tags = set()
        for song in self.itervalues():
            tags.update(song.list(tag))
        return list(tags)

    def rename(self, song, newname, changed=None):
        """Rename a song.

        This requires a special method because it can change the
        song's key.

        The 'changed' signal may fire for this library or the changed
        song is added to the passed changed set().

        If the song exists in multiple libraries you cannot use this
        method. Instead, use the librarian.
        """
        print_d("Renaming %r to %r" % (song.key, newname), self)
        del(self._contents[song.key])
        song.rename(newname)
        self._contents[song.key] = song
        if changed is not None:
            print_d("%s: Delaying changed signal." % (type(self).__name__,))
            changed.add(song)
        else:
            self.changed(set([song]))

    def query(self, text, sort=None, star=Query.STAR):
        """Query the library and return matching songs."""
        if isinstance(text, str):
            text = text.decode('utf-8')

        songs = self.values()
        if text != "":
            songs = filter(Query(text, star).search, songs)
        return songs


class FileLibrary(PicklingLibrary):
    """A library containing items on a local(-ish) filesystem.

    These must support the valid, exists, mounted, and reload methods,
    and have a mountpoint attribute.
    """

    def __init__(self, name=None):
        super(FileLibrary, self).__init__(name)
        self._masked = {}

    def _load_init(self, items):
        """Add many items to the library, check if the
        mountpoints are available and mark items as masked if not.

        Does not check if items are valid.
        """

        mounts = {}
        contents = self._contents
        masked = self._masked

        for item in items:
            mountpoint = item.mountpoint

            if mountpoint not in mounts:
                is_mounted = os.path.ismount(mountpoint)
                mounts[mountpoint] = is_mounted
                # at least one not mounted, make sure masked has an entry
                if not is_mounted:
                    masked.setdefault(mountpoint, {})

            if mounts[mountpoint]:
                contents[item.key] = item
            else:
                masked[mountpoint][item.key] = item

    def _load_item(self, item, force=False):
        """Add an item, or refresh it if it's already in the library.
        No signals will be fired.
        Return a tuple of booleans: (changed, removed)
        """
        print_d("Loading %r." % item.key, self)
        valid = item.valid()

        # The item is fine; add it if it's not present.
        if not force and valid:
            print_d("%r is valid." % item.key, self)
            self._contents[item.key] = item
            return False, False
        else:
            # Either we should force a load, or the item is not okay.
            # We're going to reload; this could change the key.  So
            # remove the item if it's currently in.
            try:
                del(self._contents[item.key])
            except KeyError:
                present = False
            else:
                present = True
            # If the item still exists, reload it.
            if item.exists():
                try:
                    item.reload()
                except (StandardError, EnvironmentError):
                    print_d("Error reloading %r." % item.key, self)
                    util.print_exc()
                    return False, True
                else:
                    print_d("Reloaded %r." % item.key, self)
                    self._contents[item.key] = item
                    return True, False
            elif not item.mounted():
                # We don't know if the item is okay or not, since
                # it's not not mounted. If the item was present
                # we need to mark it as removed.
                print_d("Masking %r." % item.key, self)
                self._masked.setdefault(item.mountpoint, {})
                self._masked[item.mountpoint][item.key] = item
                return False, present
            else:
                # The item doesn't exist at all anymore. Mark it as
                # removed if it was present, otherwise nothing.
                print_d("Ignoring (so removing) %r." % item.key, self)
                return False, present

    def reload(self, item, changed=None, removed=None):
        """Reload a song, possibly noting its status.

        If sets are given, it assumes the caller will handle signals,
        and only updates the sets. Otherwise, it handles signals
        itself. It *always* handles library contents, so do not
        try to remove (again) a song that appears in the removed set.
        """

        was_changed, was_removed = self._load_item(item, force=True)
        assert not (was_changed and was_removed)

        if was_changed:
            if changed is None:
                self.emit('changed', set([item]))
            else:
                changed.add(item)
        elif was_removed:
            if removed is None:
                self.emit('removed', set([item]))
            else:
                removed.add(item)

    def rebuild(self, paths, force=False, exclude=[], cofuncid=None):
        """Reload or remove songs if they have changed or been deleted.

        This generator rebuilds the library over the course of iteration.

        Any paths given will be scanned for new files, using the `scan`
        method.

        Only items present in the library when the rebuild is started
        will be checked.

        If this function is copooled, set `cofuncid` to enable pause/stop
        buttons in the UI.
        """

        print_d("Rebuilding, force is %s." % force, self)

        task = Task(_("Library"), _("Checking mount points"))
        if cofuncid:
            task.copool(cofuncid)
        for i, (point, items) in task.list(enumerate(self._masked.items())):
            if os.path.ismount(point):
                self._contents.update(items)
                del(self._masked[point])
                self.emit('added', items.values())
                yield True

        task = Task(_("Library"), _("Scanning library"))
        if cofuncid:
            task.copool(cofuncid)
        changed, removed = set(), set()
        for i, (key, item) in task.list(enumerate(sorted(self.items()))):
            if key in self._contents and force or not item.valid():
                self.reload(item, changed, removed)
            # These numbers are pretty empirical. We should yield more
            # often than we emit signals; that way the main loop stays
            # interactive and doesn't get bogged down in updates.
            if len(changed) > 100:
                self.emit('changed', changed)
                changed = set()
            if len(removed) > 100:
                self.emit('removed', removed)
                removed = set()
            if len(changed) > 5 or i % 100 == 0:
                yield True
        print_d("Removing %d, changing %d." % (len(removed), len(changed)),
                self)
        if removed:
            self.emit('removed', removed)
        if changed:
            self.emit('changed', changed)

        for value in self.scan(paths, exclude, cofuncid):
            yield value

    def add_filename(self, filename, add=True):
        """Add a file based on its filename.

        Subclasses must override this to open the file correctly.
        """
        raise NotImplementedError

    def scan(self, paths, exclude=[], cofuncid=None):
        added = []
        exclude = [expanduser(path) for path in exclude if path]

        def need_yield(last_yield=[0]):
            current = time.time()
            if abs(current - last_yield[0]) > 0.015:
                last_yield[0] = current
                return True
            return False

        def need_added(last_added=[0]):
            current = time.time()
            if abs(current - last_added[0]) > 1.0:
                last_added[0] = current
                return True
            return False

        for fullpath in paths:
            print_d("Scanning %r." % fullpath, self)
            desc = _("Scanning %s") % (unexpand(fsdecode(fullpath)))
            with Task(_("Library"), desc) as task:
                if cofuncid:
                    task.copool(cofuncid)
                fullpath = expanduser(fullpath)
                if filter(fullpath.startswith, exclude):
                    continue
                for path, dnames, fnames in os.walk(util.fsnative(fullpath)):
                    self._process_scanned_dirs(path, dnames)
                    for filename in fnames:
                        fullfilename = os.path.join(path, filename)
                        if filter(fullfilename.startswith, exclude):
                            continue
                        if fullfilename not in self._contents:
                            fullfilename = os.path.realpath(fullfilename)
                            # skip unknown file extensions
                            if not formats.filter(fullfilename):
                                continue
                            if filter(fullfilename.startswith, exclude):
                                continue
                            if fullfilename not in self._contents:
                                item = self.add_filename(fullfilename, False)
                                if item is not None:
                                    added.append(item)
                                    if len(added) > 100 or need_added():
                                        self.add(added)
                                        added = []
                                        task.pulse()
                                        yield
                                if added and need_yield():
                                    yield
                if added:
                    self.add(added)
                    added = []
                    task.pulse()
                    yield True

    def _process_scanned_dirs(self, path, dirs):
        """Visitor for directories `dirs` in `path` that have just been
        scanned"""
        pass

    def start_watching(self):
        """Subclasses should implement this to set up watches on their
        content"""
        print_w("File watching not configured.")
        pass

    def stop_watching(self):
        """Subclasses should implement this to destroy watches"""
        print_w("File watching not configured.")
        pass

    def get_content(self):
        """Return visible and masked items"""

        items = self.values()
        for masked in self._masked.values():
            items.extend(masked.values())

        # Item keys are often based on filenames, in which case
        # sorting takes advantage of the filesystem cache when we
        # reload/rescan the files.
        items.sort(key=lambda item: item.key)

        return items

    def masked(self, item):
        """Return true if the item is in the library but masked."""
        try:
            point = item.mountpoint
        except AttributeError:
            # Checking a key.
            for point in self._masked.itervalues():
                if item in point:
                    return True
        else:
            # Checking a full item.
            return item in self._masked.get(point, {}).itervalues()

    def unmask(self, point):
        print_d("Unmasking %r." % point, self)
        items = self._masked.pop(point, {})
        if items:
            self.add(items.values())

    def mask(self, point):
        print_d("Masking %r." % point, self)
        removed = {}
        for item in self.itervalues():
            if item.mountpoint == point:
                removed[item.key] = item
        if removed:
            self.remove(removed.values())
            self._masked.setdefault(point, {}).update(removed)

    @property
    def masked_mount_points(self):
        """List of mount points that contain masked items"""

        return self._masked.keys()

    def get_masked(self, mount_point):
        """List of items for a mount point"""

        return self._masked.get(mount_point, {}).values()

    def remove_masked(self, mount_point):
        """Remove all songs for a masked point"""

        self._masked.pop(mount_point, {})


class WatchedFileLibrary(FileLibrary):
    """A File Library that sets up monitors on directories at refresh
    and handles changes sensibly"""

    def __init__(self, name=None):
        super(WatchedFileLibrary, self).__init__(name)
        self.__monitors = {}

    def monitor_dir(self, path):
        """Monitors a single directory"""

        assert is_fsnative(path)

        normalised = normalize_path(path, True)
        # Only add one monitor per absolute path...
        if normalised not in self.__monitors:
            f = Gio.File.new_for_path(fsencode(normalised))
            try:
                monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            except GLib.GError:
                return
            handler_id = monitor.connect("changed", self.__file_changed)
            # Don't destroy references - http://stackoverflow.com/q/4535227
            self.__monitors[path] = (monitor, handler_id)

    def __file_changed(self, monitor, main_file, other_file, event):
        file_path = main_file.get_path()
        if file_path is None:
            return
        file_path = normalize_path(util.fsnative(file_path), True)

        if event == Gio.FileMonitorEvent.CREATED:
            if os.path.isdir(file_path):
                print_d("Monitoring new directory %s" % (file_path,))
                self.monitor_dir(file_path)
                for _ in self.scan([file_path]):
                    # Just consume.
                    pass
                return
            else:
                song = self.get(file_path)
                if song:
                    # QL created this one; still check if it changed
                    if not song.valid():
                        self.reload(song)
                else:
                    print_d("Auto-adding new file: %s" % file_path)
                    self.add_filename(file_path)
        elif event == Gio.FileMonitorEvent.DELETED:
            song = self.get(file_path)
            if song:
                print_d("Auto-removing song: %s" % file_path)
                self.reload(song)
            else:
                # either not a song, or a song that was renamed by QL
                if self.is_monitored_dir(file_path):
                    self.unmonitor_dir(file_path)
                # Make sure they are in this sub-dir, not similar files
                path_fragment = (file_path if file_path.endswith(os.sep)
                                 else file_path + os.sep)

                # And try to remove all songs under that dir. Slowly.
                gone = []
                for key, song in self.iteritems():
                    if key.startswith(path_fragment):
                        gone.append(song)
                if gone:
                    print_d("Removing %d songs in %s" % (len(gone), file_path))
                    self.remove(gone)
        elif event == Gio.FileMonitorEvent.CHANGED:
            song = self.get(file_path)
            if song and not song.valid():
                print_d("Updating externally changed song: %s" % file_path)
                self.reload(song)
        elif event == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            # TODO: should we wait till changes are finished?
            # Doesn't seem to have much value
            pass
        elif event == Gio.FileMonitorEvent.ATTRIBUTE_CHANGED:
            # Probably pointless for us.
            pass
        else:
            print_d("Unhandled event %s on %s" % (event, file_path))

    def is_monitored_dir(self, path):
        assert is_fsnative(path)
        return path in self.__monitors

    def unmonitor_dir(self, path):
        """Disconnect and remove any monitor for a directory, if found"""

        assert is_fsnative(path)

        monitor, handler_id = self.__monitors.get(path, (None, None))
        if not monitor:
            print_d("Couldn't find path %s in active monitors" % path)
            return
        monitor.disconnect(handler_id)
        del self.__monitors[path]

    def _process_scanned_dirs(self, base, dirs):
        super(WatchedFileLibrary, self)._process_scanned_dirs(base, dirs)
        # Shortcut out of iteration
        if not config.getboolean("library", "auto_update"):
            return
        for d in dirs:
            self.monitor_dir(os.path.join(base, d))

    def start_watching(self):
        paths = get_scan_dirs()
        print_d("Setting up file watches for %s on %s..."
                % (type(self), paths))
        exclude = [expanduser(e) for e in get_excluded_scan_dirs() if e]

        def watching_producer():
            # TODO: integrate this better with scanning.
            for fullpath in paths:
                desc = _("Adding watches for %s") % (
                    unexpand(fsdecode(fullpath)))
                with Task(_("Library"), desc) as task:
                    fullpath = expanduser(fullpath)
                    if filter(fullpath.startswith, exclude):
                        continue
                    unpulsed = 0
                    for path, dirs, files in os.walk(fullpath):
                        for d in dirs:
                            self.monitor_dir(os.path.join(path, d))
                        unpulsed += len(dirs)
                        if unpulsed > 50:
                            task.pulse()
                            unpulsed = 0
                        yield

        copool.add(watching_producer, funcid="watch_library")

    def stop_watching(self):
        for path in self.__monitors.keys():
            self.unmonitor_dir(path)

    def destroy(self):
        self.stop_watching()
        super(WatchedFileLibrary, self).destroy()


class SongFileLibrary(SongLibrary, WatchedFileLibrary):
    """A library containing song files.
    Pickles contents to disk as `FileLibrary`"""

    def __init__(self, name=None):
        print_d("Initializing SongFileLibrary \"%s\"." % name)
        super(SongFileLibrary, self).__init__(name)

    def add_filename(self, filename, add=True):
        """Add a song to the library based on filename.

        If 'add' is true, the song will be added and the 'added' signal
        may be fired.

        Example (add=False):
            load many songs and call Library.add(songs) to add all in one go.

        The song is returned if it is in the library after this call.
        Otherwise, None is returned.
        """

        song = None
        if filename not in self._contents:
            song = MusicFile(filename)
            if song and add:
                self.add([song])
        else:
            print_d("Already got file %r." % filename)
            song = self._contents[filename]

        return song
