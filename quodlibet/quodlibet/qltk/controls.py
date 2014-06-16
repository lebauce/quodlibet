# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

from gi.repository import Gtk, GLib, Gdk

from quodlibet import config
from quodlibet import qltk
from quodlibet.qltk import bookmarks
from quodlibet import util

from quodlibet.qltk.ccb import ConfigCheckMenuItem
from quodlibet.qltk.sliderbutton import HSlider
from quodlibet.qltk.tracker import TimeTracker
from quodlibet.qltk.x import (RadioMenuItem, SeparatorMenuItem,
                              SymbolicIconImage)


class TimeLabel(Gtk.Label):
    """A label for displaying the running time

    It tries to minimize size changes due to unequal character widths
    with the same number of characters.

    e.g. a time display -> 04:20
    """

    def __init__(self, time_=0):
        Gtk.Label.__init__(self)
        self.__widths = {}  # num-chars -> (max-min-width, max-natural-width)
        self.set_time(time_)

    def do_get_preferred_width(self):
        widths = Gtk.Label.do_get_preferred_width(self)

        # If for same number of characters, the needed width was larger,
        # use that instead of the current one
        num_chars = len(self.get_text().decode("utf-8"))
        max_widths = self.__widths.get(num_chars, widths)
        widths = max(widths[0], max_widths[0]), max(widths[1], max_widths[1])
        self.__widths[num_chars] = widths
        return widths

    def set_time(self, time_):
        """Set the time in seconds"""

        self.set_text(util.format_time(time_))


class SeekBar(HSlider):
    __lock = False
    __sig = None
    __seekable = True

    def __init__(self, player, library):
        hbox = Gtk.HBox(spacing=3)
        l = TimeLabel()
        hbox.pack_start(l, True, True, 0)
        arrow = Gtk.Arrow.new(Gtk.ArrowType.RIGHT, Gtk.ShadowType.NONE)
        hbox.pack_start(arrow, False, True, 0)
        super(SeekBar, self).__init__(hbox)

        self._slider_label = TimeLabel()
        self.set_slider_widget(self._slider_label)

        self.scale.connect('button-press-event', self.__seek_lock)
        self.scale.connect('button-release-event', self.__seek_unlock, player)
        self.scale.connect('key-press-event', self.__seek_lock)
        self.scale.connect('key-release-event', self.__seek_unlock, player)
        self.connect('scroll-event', self.__scroll, player)
        self.scale.connect('value-changed', self.__update_time, l)

        m = Gtk.Menu()
        c = ConfigCheckMenuItem(
            _("Display remaining time"), "player", "time_remaining")
        c.set_active(config.getboolean("player", "time_remaining"))
        c.connect_object('toggled', self.scale.emit, 'value-changed')
        self.__remaining = c
        m.append(c)
        m.append(SeparatorMenuItem())
        i = qltk.MenuItem(_("_Edit Bookmarks..."), Gtk.STOCK_EDIT)

        def edit_bookmarks_cb(menu_item):
            window = bookmarks.EditBookmarks(self, library, player)
            window.show()

        i.connect('activate', edit_bookmarks_cb)
        m.append(i)
        m.show_all()
        self.connect_object(
            'button-press-event', self.__check_menu, m, player, c)
        self.connect_object('popup-menu', self.__popup_menu, m, player)

        timer = TimeTracker(player)
        timer.connect_object('tick', self.__check_time, player)

        player.connect('song-started', self.__song_changed, l, m)
        player.connect('seek', self.__seeked)

    def __check_menu(self, menu, event, player, remaining_item):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return

        if event.button == Gdk.BUTTON_SECONDARY:
            return self.__popup_menu(menu, player, event)
        elif event.button == Gdk.BUTTON_MIDDLE:
            remaining_item.set_active(not remaining_item.get_active())
            return True

    def __popup_menu(self, menu, player, event=None):
        for child in menu.get_children()[2:-1]:
            menu.remove(child)
            child.destroy()

        try:
            marks = player.song.bookmarks
        except AttributeError:
            # song is None
            pass
        else:
            items = qltk.bookmarks.MenuItems(marks, player, self.__seekable)
            items.reverse()
            for i in items:
                menu.insert(i, 2)

        if event:
            menu.popup(None, None, None, None, 3, event.time)
            return True
        else:
            time = Gtk.get_current_event_time()
            return qltk.popup_menu_under_widget(menu, self, 3, time)

    def __seeked(self, player, song, ms):
        # If it's not paused, we'll grab it in our next update.
        if player.paused:
            self.scale.set_value(ms // 1000)

    def __scroll(self, widget, event, player):
        self.__lock = True
        if self.__sig is not None:
            GLib.source_remove(self.__sig)
        self.__sig = GLib.timeout_add(100, self.__scroll_timeout, player)

    def __scroll_timeout(self, player):
        self.__lock = False
        if self.__seekable:
            player.seek(self.scale.get_value() * 1000)
        self.__sig = None

    def __seek_lock(self, scale, event):
        self.__lock = True

    def __seek_unlock(self, scale, event, player):
        self.__lock = False
        if self.__seekable:
            player.seek(self.scale.get_value() * 1000)

    def __check_time(self, player):
        # When the song is paused GStreamer returns < 1 for position
        # queries, so if it's paused just ignore it.
        if not (player.paused or self.__lock):
            position = player.get_position() // 1000
            if (not self.__seekable and
                position > self.scale.get_adjustment().get_upper()):
                self.scale.set_range(0, position)
            self.scale.set_value(position)
        return True

    def __update_time(self, scale, timer):
        value = scale.get_value()
        max_ = scale.get_adjustment().get_upper()
        remaining = value - max_
        if self.__remaining.get_active():
            remaining, value = value, remaining
        timer.set_time(value)
        self._slider_label.set_time(remaining)

    def __song_changed(self, player, song, label, menu):

        if song and song("~#length") > 0:
            self.scale.set_range(0, song("~#length"))
            slider_width = song("~#length")
            self.__seekable = True
        else:
            self.scale.set_range(0, 1)
            slider_width = 0
            self.__seekable = False

        self.scale.set_value(0)

        slider_width = min(max(slider_width, 170), 400)
        self.set_slider_length(slider_width)

        for child in menu.get_children()[2:-1]:
            menu.remove(child)
            child.destroy()
        menu.get_children()[-1].set_sensitive(self.__seekable)
        self.scale.emit('value-changed')


class Volume(Gtk.VolumeButton):
    def __init__(self, device):
        super(Volume, self).__init__(size=Gtk.IconSize.MENU, use_symbolic=True)

        self.set_relief(Gtk.ReliefStyle.NORMAL)
        self.set_adjustment(Gtk.Adjustment.new(0, 0, 1, 0.05, 0.1, 0))

        self.connect('value-changed', self.__volume_changed, device)
        device.connect('notify::volume', self.__volume_notify)
        self.set_value(config.getfloat("memory", "volume"))

        replaygain_menu = ReplayGainMenu(device)
        self.connect('popup-menu', self.__popup, replaygain_menu)
        self.connect_object('button-press-event', self.__volume_button_press,
                            replaygain_menu)

    def __popup(self, widget, menu):
        time = Gtk.get_current_event_time()
        button = 3
        return qltk.popup_menu_under_widget(menu, widget, button, time)

    def __volume_button_press(self, menu, event):
        if event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)
            return True

    def __iadd__(self, v):
        self.set_value(self.get_value() + v)
        return self

    def __isub__(self, v):
        self.set_value(self.get_value() - v)
        return self

    def __volume_changed(self, button, volume, device):
        config.set("memory", "volume", str(volume))
        device.volume = volume

    def __volume_notify(self, device, prop):
        self.set_value(device.props.volume)


class ReplayGainMenu(Gtk.Menu):
    __modes = (
        ("auto", _("Auto_matic"), None),
        ("track", _("_Track Mode"), ["track"]),
        ("album", _("_Album Mode"), ["album", "track"])
    )

    def __init__(self, player):
        super(ReplayGainMenu, self).__init__()

        item = None
        for mode, title, profile in self.__modes:
            item = RadioMenuItem(group=item, label=title,
                                 use_underline=True)
            self.append(item)
            item.connect("toggled", self.__changed, player, profile)
            if player.replaygain_profiles[0] == profile:
                item.set_active(True)
            item.show()

    def __changed(self, item, player, profile):
        if item.get_active():
            player.replaygain_profiles[0] = profile
            player.volume = player.volume

    def popup(self, *args):
        gain = config.getboolean("player", "replaygain")
        for child in self.get_children():
            child.set_sensitive(gain)
        return super(ReplayGainMenu, self).popup(*args)


class PlayControls(Gtk.VBox):
    def __init__(self, player, library):
        super(PlayControls, self).__init__(spacing=3)

        upper = Gtk.Table(n_rows=1, n_columns=3, homogeneous=True)
        upper.set_row_spacings(3)
        upper.set_col_spacings(3)

        prev = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        prev.add(SymbolicIconImage("media-skip-backward",
                                   Gtk.IconSize.LARGE_TOOLBAR))
        upper.attach(prev, 0, 1, 0, 1)

        play = Gtk.ToggleButton(relief=Gtk.ReliefStyle.NONE)
        play.add(SymbolicIconImage("media-playback-start",
                                   Gtk.IconSize.LARGE_TOOLBAR))
        upper.attach(play, 1, 2, 0, 1)

        next_ = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        next_.add(SymbolicIconImage("media-skip-forward",
                                    Gtk.IconSize.LARGE_TOOLBAR))
        upper.attach(next_, 2, 3, 0, 1)

        lower = Gtk.Table(n_rows=1, n_columns=3, homogeneous=True)
        lower.set_row_spacings(3)
        lower.set_col_spacings(3)

        self.volume = Volume(player)
        self.volume.set_relief(Gtk.ReliefStyle.NONE)
        lower.attach(self.volume, 0, 1, 0, 1)

        seekbar = SeekBar(player, library)
        seekbar.set_relief(Gtk.ReliefStyle.NONE)
        lower.attach(seekbar, 1, 3, 0, 1)

        self.pack_start(upper, False, True, 0)
        self.pack_start(lower, False, True, 0)

        prev.connect_object('clicked', self.__previous, player)
        play.connect('toggled', self.__playpause, player)
        play.add_events(Gdk.EventMask.SCROLL_MASK)
        play.connect_object('scroll-event', self.__scroll, player)
        next_.connect_object('clicked', self.__next, player)
        player.connect('song-started', self.__song_started, next_, play)
        player.connect_object('paused', play.set_active, False)
        player.connect_object('unpaused', play.set_active, True)

    def __scroll(self, player, event):
        if event.direction in [Gdk.ScrollDirection.UP,
                               Gdk.ScrollDirection.LEFT]:
            player.previous()
        elif event.direction in [Gdk.ScrollDirection.DOWN,
                                 Gdk.ScrollDirection.RIGHT]:
            player.next()

    def __song_started(self, player, song, next, play):
        play.set_active(not player.paused)

    def __playpause(self, button, player):
        if button.get_active() and player.song is None:
            player.reset()
            button.set_active(not player.paused)
        else:
            player.paused = not button.get_active()

    def __previous(self, player):
        player.previous()

    def __next(self, player):
        player.next()
