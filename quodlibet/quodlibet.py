#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#           2012, 2013 Christoph Reiter
# <quod-libet-development@googlegroups.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import sys
import os

if sys.version_info[0] != 2:
    try:
        os.execvp("python2", ["python"] + sys.argv)
    except OSError:
        pass

import signal
import sys
import tempfile
import stat

play = False
no_plugins = False


def main():
    process_arguments()

    from quodlibet import const
    if isrunning() and not const.DEBUG:
        print_(_("Quod Libet is already running."))
        control('focus')

    import quodlibet
    from quodlibet import app
    quodlibet._init_signal(app.quit)

    import quodlibet.player
    from quodlibet import config
    from quodlibet import browsers
    from quodlibet import const
    from quodlibet import util

    config.init(const.CONFIG)

    library = quodlibet.init(library=const.LIBRARY,
                             icon="quodlibet",
                             name="Quod Libet",
                             title=const.PROCESS_TITLE_QL)
    app.library = library

    from quodlibet.player import PlayerError
    # this assumes that nullbe will always succeed
    for backend in [config.get("player", "backend"), "nullbe"]:
        try:
            player = quodlibet.init_backend(backend, app.librarian)
        except PlayerError as error:
            print_e("%s. %s" % (error.short_desc, error.long_desc))
        else:
            break
    app.player = player

    os.environ["PULSE_PROP_media.role"] = "music"
    os.environ["PULSE_PROP_application.icon_name"] = "quodlibet"

    browsers.init()

    from quodlibet.qltk.songlist import SongList

    from quodlibet.util.collection import Album
    try:
        cover_size = config.getint("browsers", "cover_size")
    except config.Error:
        pass
    else:
        if cover_size > 0:
            Album.COVER_SIZE = cover_size

    headers = config.get_columns()
    SongList.set_all_column_headers(headers)

    for opt in config.options("header_maps"):
        val = config.get("header_maps", opt)
        util.tags.add(opt, val)

    in_all = ("~filename ~uri ~#lastplayed ~#rating ~#playcount ~#skipcount "
              "~#added ~#bitrate ~current ~#laststarted ~basename "
              "~dirname").split()
    for Kind in browsers.browsers:
        if Kind.headers is not None:
            Kind.headers.extend(in_all)
        Kind.init(library)

    pm = quodlibet.init_plugins(no_plugins)

    if hasattr(player, "init_plugins"):
        player.init_plugins()

    from quodlibet.qltk import unity
    unity.init("quodlibet.desktop", player)

    from quodlibet.qltk.songsmenu import SongsMenu
    SongsMenu.init_plugins()
    from quodlibet.util.cover.manager import cover_plugins
    cover_plugins.init_plugins()
    from quodlibet.plugins.playlist import PLAYLIST_HANDLER
    PLAYLIST_HANDLER.init_plugins()

    from quodlibet.qltk.quodlibetwindow import QuodLibetWindow
    app.window = window = QuodLibetWindow(library, player)

    from quodlibet.plugins.events import EventPluginHandler
    pm.register_handler(EventPluginHandler(library.librarian, player))

    from quodlibet.qltk import mmkeys_ as mmkeys
    from quodlibet.qltk.remote import FSInterface, FIFOControl
    from quodlibet.qltk.tracker import SongTracker
    try:
        from quodlibet.qltk.dbus_ import DBusHandler
    except ImportError:
        DBusHandler = lambda player, library: None

    mmkeys.init(window, player)
    fsiface = FSInterface(player)
    quodlibet.quit_add(1, fsiface.destroy)

    fifoctrl = FIFOControl(app)
    quodlibet.quit_add(1, fifoctrl.destroy)

    DBusHandler(player, library)
    SongTracker(library.librarian, player, window.playlist)

    from quodlibet.qltk import session
    session.init("quodlibet")

    quodlibet.enable_periodic_save(save_library=True)

    if play:
        player.paused = False

    # restore browser windows
    from quodlibet.qltk.browser import LibraryBrowser
    from gi.repository import GLib
    GLib.idle_add(LibraryBrowser.restore, library, priority=GLib.PRIORITY_HIGH)

    quodlibet.main(window)

    print_d("Shutting down player device %r." % player.version_info)
    player.destroy()
    quodlibet.library.save(force=True)

    config.save(const.CONFIG)

    print_d("Finished shutdown.")


def print_fifo(command):
    import quodlibet
    from quodlibet import const

    if not os.path.exists(const.CURRENT):
        quodlibet.exit("not-running")
    else:
        fd, filename = tempfile.mkstemp()
        try:
            os.unlink(filename)
            # mkfifo fails if the file exists, so this is safe.
            os.mkfifo(filename, 0o600)

            signal.signal(signal.SIGALRM, lambda: "" + 2)
            signal.alarm(1)
            f = file(const.CONTROL, "w")
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
            f.write(command + " " + filename)
            f.close()

            f = file(filename, "r")
            sys.stdout.write(f.read())
            try:
                os.unlink(filename)
            except EnvironmentError:
                pass
            f.close()
            quodlibet.exit()
        except TypeError:
            try:
                os.unlink(filename)
            except EnvironmentError:
                pass
            quodlibet.exit("not-running")


def print_playing(fstring="<artist~album~tracknumber~title>"):
    import quodlibet
    from quodlibet.formats._audio import AudioFile
    from quodlibet.parse import Pattern
    from quodlibet import const

    try:
        text = open(const.CURRENT, "rb").read()
        song = AudioFile()
        song.from_dump(text)
        print_(Pattern(fstring).format(song))
        quodlibet.exit()
    except (OSError, IOError):
        print_(_("No song is currently playing."))
        quodlibet.exit(True)


def print_query(query):
    '''Queries library, dumping filenames of matches to stdout

        See Issue 716
    '''

    import quodlibet
    import quodlibet.library
    from quodlibet import const

    print_d("Querying library for %r" % query)

    library = quodlibet.library.init(const.LIBRARY)
    songs = library.query(query)
    #songs.sort()
    sys.stdout.write("\n".join([song("~filename") for song in songs]) + "\n")
    quodlibet.exit()


def isrunning():
    from quodlibet import const

    # http://code.google.com/p/quodlibet/issues/detail?id=1131
    # FIXME: There is a race where control() creates a new file
    # instead of writing to the fifo, confusing the next QL instance.
    # Remove non-fifos here for now.
    try:
        if not stat.S_ISFIFO(os.stat(const.CONTROL).st_mode):
            print_d("%r not a FIFO. Remove it." % const.CONTROL)
            os.remove(const.CONTROL)
    except OSError:
        pass
    return os.path.exists(const.CONTROL)


def control(c):
    import quodlibet
    from quodlibet import const

    if not isrunning():
        quodlibet.exit(_("Quod Libet is not running."), notify_startup=True)
    else:
        try:
            # This is a total abuse of Python! Hooray!
            signal.signal(signal.SIGALRM, lambda: "" + 2)
            signal.alarm(1)
            f = file(const.CONTROL, "w")
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
            f.write(c)
            f.close()
        except (OSError, IOError, TypeError):
            print_w(_("Unable to write to %s. Removing it.") % const.CONTROL)
            try:
                os.unlink(const.CONTROL)
            except OSError:
                pass
            if c != 'focus':
                raise quodlibet.exit(True, notify_startup=True)
        else:
            quodlibet.exit(notify_startup=True)


def process_arguments():
    import quodlibet
    from quodlibet.util.uri import URI
    from quodlibet import util
    from quodlibet import const

    controls = ["next", "previous", "play", "pause", "play-pause", "stop",
                "hide-window", "show-window", "toggle-window",
                "focus", "quit", "unfilter", "refresh", "force-previous"]
    controls_opt = ["seek", "order", "repeat", "query", "volume", "filter",
                    "set-rating", "set-browser", "open-browser", "random",
                    "song-list", "queue"]

    options = util.OptionParser(
        "Quod Libet", const.VERSION,
        _("a music library and player"),
        _("[option]"))

    options.add("print-playing", help=_("Print the playing song and exit"))
    options.add("start-playing", help=_("Begin playing immediately"))

    for opt, help in [
        ("next", _("Jump to next song")),
        ("previous",
            _("Jump to previous song or restart if near the beginning")),
        ("force-previous", _("Jump to previous song")),
        ("play", _("Start playback")),
        ("pause", _("Pause playback")),
        ("play-pause", _("Toggle play/pause mode")),
        ("stop", _("Stop playback")),
        ("volume-up", _("Turn up volume")),
        ("volume-down", _("Turn down volume")),
        ("status", _("Print player status")),
        ("hide-window", _("Hide main window")),
        ("show-window", _("Show main window")),
        ("toggle-window", _("Toggle main window visibility")),
        ("focus", _("Focus the running player")),
        ("unfilter", _("Remove active browser filters")),
        ("refresh", _("Refresh and rescan library")),
        ("list-browsers", _("List available browsers")),
        ("print-playlist", _("Print the current playlist")),
        ("print-queue", _("Print the contents of the queue")),
        ("no-plugins", _("Start without plugins")),
        ("quit", _("Exit Quod Libet")),
            ]:
        options.add(opt, help=help)

    for opt, help, arg in [
        ("seek", _("Seek within the playing song"), _("[+|-][HH:]MM:SS")),
        ("order", _("Set or toggle the playback order"),
            "[order]|toggle"),
        ("repeat", _("Turn repeat off, on, or toggle it"), "0|1|t"),
        ("volume", _("Set the volume"), "(+|-|)0..100"),
        ("query", _("Search your audio library"), _("query")),
        ("play-file", _("Play a file"), Q_("command|filename")),
        ("set-rating", _("Rate the playing song"), "0.0..1.0"),
        ("set-browser", _("Set the current browser"), "BrowserName"),
        ("open-browser", _("Open a new browser"), "BrowserName"),
        ("queue", _("Show or hide the queue"), "on|off|t"),
        ("song-list", _("Show or hide the main song list"), "on|off|t"),
        ("random", _("Filter on a random value"), Q_("command|tag")),
        ("filter", _("Filter on a tag value"), _("tag=value")),
        ("enqueue", _("Enqueue a file or query"), "%s|%s" % (
            Q_("command|filename"), _("query"))),
        ("enqueue-files", _("Enqueue comma-separated files"), "%s[,%s..]" % (
            _("filename"), _("filename"))),
        ("print-query", _("Print filenames of results of query to stdout"),
            _("query")),
        ("unqueue", _("Unqueue a file or query"), "%s|%s" % (
            Q_("command|filename"), _("query"))),
            ]:
        options.add(opt, help=help, arg=arg)

    options.add("sm-config-prefix", arg="dummy")
    options.add("sm-client-id", arg="prefix")
    options.add("screen", arg="dummy")

    def is_vol(str):
        if str[0] in '+-':
            if len(str) == 1:
                return True
            str = str[1:]
        return str.isdigit()

    def is_time(str):
        if str[0] not in "+-0123456789":
            return False
        elif str[0] in "+-":
            str = str[1:]
        parts = str.split(":")
        if len(parts) > 3:
            return False
        else:
            return not (False in [p.isdigit() for p in parts])

    def is_float(str):
        try:
            float(str)
        except ValueError:
            return False
        else:
            return True

    validators = {
        "order": ["0", "1", "t", "toggle", "inorder", "shuffle",
                  "weighted", "onesong"].__contains__,
        "repeat": ["0", "1", "t", "on", "off", "toggle"].__contains__,
        "volume": is_vol,
        "seek": is_time,
        "set-rating": is_float,
        }

    opts, args = options.parse()
    for command, arg in opts.items():
        if command in controls:
            control(command)
        elif command in controls_opt:
            if command in validators and not validators[command](arg):
                print_e(_("Invalid argument for '%s'.") % command)
                print_e(_("Try %s --help.") % sys.argv[0])
                quodlibet.exit(True, notify_startup=True)
            else:
                control(command + " " + arg)
        elif command == "status":
            print_fifo("status")
        elif command == "print-playlist":
            print_fifo("dump-playlist")
        elif command == "print-queue":
            print_fifo("dump-queue")
        elif command == "list-browsers":
            print_fifo("dump-browsers")
        elif command == "volume-up":
            control("volume +")
        elif command == "volume-down":
            control("volume -")
        elif command == "enqueue" or command == "unqueue":
            try:
                filename = URI(arg).filename
            except ValueError:
                filename = arg
            control(command + " " + filename)
        elif command == "enqueue-files":
            control(command + " " + arg)
        elif command == "play-file":
            try:
                filename = URI(arg).filename
            except ValueError:
                filename = os.path.abspath(util.path.expanduser(arg))
            if os.path.isdir(filename):
                control("add-directory " + filename)
            else:
                control("add-file " + filename)
        elif command == "print-playing":
            try:
                print_playing(args[0])
            except IndexError:
                print_playing()
        elif command == "print-query":
            print_query(arg)
        elif command == "start-playing":
            global play
            play = True
        elif command == "no-plugins":
            global no_plugins
            no_plugins = True

if __name__ == "__main__":
    main()
