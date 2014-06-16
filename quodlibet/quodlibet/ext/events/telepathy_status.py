# -*- coding: utf-8 -*-
# Quod Libet Telepathy Plugin
# Copyright 2012 Nick Boultbee, Christoph Reiter
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

if os.name == "nt":
    from quodlibet.plugins import PluginNotSupportedError
    raise PluginNotSupportedError

import dbus
from gi.repository import Gtk

from quodlibet.parse._pattern import Pattern
from quodlibet.qltk.entry import UndoEntry
from quodlibet import util
from quodlibet import qltk

from quodlibet.plugins.events import EventPlugin
from quodlibet.plugins import PluginConfigMixin
from quodlibet.util.dprint import print_d


AM_PATH = "/org/freedesktop/Telepathy/AccountManager"
AM_NAME = "org.freedesktop.Telepathy.AccountManager"
AM_IFACE = "org.freedesktop.Telepathy.AccountManager"
AC_IFACE = "org.freedesktop.Telepathy.Account"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
CONN_PRESENCE_TYPE_AVAILABLE = 2
is_valid_presence_type = lambda x: x not in [0, 7, 8]


def get_active_account_paths():
    bus = dbus.SessionBus()
    bus_object = bus.get_object(AM_NAME, AM_PATH)
    bus_iface = dbus.Interface(bus_object, dbus_interface=PROPS_IFACE)
    return bus_iface.Get(AM_IFACE, "ValidAccounts")


def set_accounts_requested_presence(paths, message):
    bus = dbus.SessionBus()
    for path in paths:
        bus_object = bus.get_object(AM_NAME, path)
        bus_iface = dbus.Interface(bus_object, dbus_interface=PROPS_IFACE)
        presence_type, status = bus_iface.Get(AC_IFACE, "CurrentPresence")[:2]
        if not is_valid_presence_type(presence_type):
            presence_type = dbus.UInt32(CONN_PRESENCE_TYPE_AVAILABLE)
        value = dbus.Struct([presence_type, status, message])
        bus_iface.Set(AC_IFACE, "RequestedPresence", value)


class TelepathyStatusPlugin(EventPlugin, PluginConfigMixin):
    PLUGIN_ID = "Telepathy Status"
    PLUGIN_NAME = _("Telepathy Status Messages")
    PLUGIN_DESC = _("Updates all Telepathy-based IM accounts (as configured "
                    "in Empathy etc) with a status message based on current "
                    "song.")
    PLUGIN_ICON = Gtk.STOCK_CONNECT
    PLUGIN_VERSION = "0.3"

    DEFAULT_PAT = "♫ <~artist~title> ♫"
    DEFAULT_PAT_PAUSED = "<~artist~title> [%s]" % _("paused")
    CFG_STATUS_SONGLESS = 'no_song_text'
    CFG_LEAVE_STATUS = "leave_status"
    CFG_PAT_PLAYING = "playing_pattern"
    CFG_PAT_PAUSED = "paused_pattern"

    def _set_status(self, text):
        print_d("Setting status to \"%s\"..." % text)
        self.status = text
        try:
            accounts = get_active_account_paths()
            # TODO: account filtering
            set_accounts_requested_presence(accounts, text)
        except dbus.DBusException:
            print_d("...but setting failed")
            util.print_exc()

    def plugin_on_song_started(self, song):
        self.song = song
        pat_str = self.config_get(self.CFG_PAT_PLAYING, self.DEFAULT_PAT)
        pattern = Pattern(pat_str)
        status = (pattern.format(song) if song
                       else self.config_get(self.CFG_STATUS_SONGLESS, ""))
        self._set_status(status)

    def plugin_on_paused(self):
        pat_str = self.config_get(self.CFG_PAT_PAUSED, self.DEFAULT_PAT_PAUSED)
        pattern = Pattern(pat_str)
        self.status = pattern.format(self.song) if self.song else ""
        self._set_status(self.status)

    def plugin_on_unpaused(self):
        self.plugin_on_song_started(self.song)

    def disabled(self):
        if self.status:
            self._set_status(self.config_get(self.CFG_STATUS_SONGLESS))

    def enabled(self):
        self.song = None
        self.status = ""

    def PluginPreferences(self, parent):
        outer_vb = Gtk.VBox(spacing=12)
        vb = Gtk.VBox(spacing=12)

        # Playing
        hb = Gtk.HBox(spacing=6)
        entry = UndoEntry()
        entry.set_text(self.config_get(self.CFG_PAT_PLAYING,
                                       self.DEFAULT_PAT))
        entry.connect('changed', self.config_entry_changed,
                      self.CFG_PAT_PLAYING)
        lbl = Gtk.Label(label=_("Playing:"))
        entry.set_tooltip_markup(_("Status text when a song is started. "
                                 "Accepts QL Patterns e.g. <tt>%s</tt>")
                                 % util.escape("<~artist~title>"))
        lbl.set_mnemonic_widget(entry)
        hb.pack_start(lbl, False, True, 0)
        hb.pack_start(entry, True, True, 0)
        vb.pack_start(hb, True, True, 0)

        # Paused
        hb = Gtk.HBox(spacing=6)
        entry = UndoEntry()
        entry.set_text(self.config_get(self.CFG_PAT_PAUSED,
                                    self.DEFAULT_PAT_PAUSED))
        entry.connect('changed', self.config_entry_changed,
                      self.CFG_PAT_PAUSED)
        lbl = Gtk.Label(label=_("Paused:"))
        entry.set_tooltip_markup(_("Status text when a song is paused. "
                                   "Accepts QL Patterns e.g. <tt>%s</tt>")
                                   % util.escape("<~artist~title>"))
        lbl.set_mnemonic_widget(entry)
        hb.pack_start(lbl, False, True, 0)
        hb.pack_start(entry, True, True, 0)
        vb.pack_start(hb, True, True, 0)

        # No Song
        hb = Gtk.HBox(spacing=6)
        entry = UndoEntry()
        entry.set_text(self.config_get(self.CFG_STATUS_SONGLESS, ""))
        entry.connect('changed', self.config_entry_changed,
                      self.CFG_STATUS_SONGLESS)
        entry.set_tooltip_text(
                _("Plain text for status when there is no current song"))
        lbl = Gtk.Label(label=_("No song:"))
        lbl.set_mnemonic_widget(entry)
        hb.pack_start(lbl, False, True, 0)
        hb.pack_start(entry, True, True, 0)
        vb.pack_start(hb, True, True, 0)

        # Frame
        frame = qltk.Frame(_("Status Patterns"), child=vb)
        outer_vb.pack_start(frame, False, True, 0)

        return outer_vb
