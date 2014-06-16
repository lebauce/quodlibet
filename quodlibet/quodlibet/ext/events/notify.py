# -*- coding: utf-8 -*-
# Copyright (c) 2010 Felix Krull <f_krull@gmx.de>
#               2011-2013 Christoph Reiter <reiter.christoph@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.


# Note: This plugin is based on notify.py as distributed in the
# quodlibet-plugins package; however, that file doesn't contain a copyright
# note. As for the license, GPLv2 is the only choice anyway, as it calls
# Quod Libet code, which is GPLv2 as well, so I thought it safe to add this.

import os

if os.name == "nt":
    from quodlibet.plugins import PluginNotSupportedError
    raise PluginNotSupportedError

import re
import tempfile

import dbus
from gi.repository import Gtk, GObject, GLib

from quodlibet import config, qltk, app
from quodlibet.plugins.events import EventPlugin
from quodlibet.parse import XMLFromPattern
from quodlibet.qltk.textedit import TextView, TextBuffer
from quodlibet.qltk.entry import UndoEntry
from quodlibet.qltk.msg import ErrorMessage
from quodlibet.util import unescape
from quodlibet.util.uri import URI

# configuration stuff
DEFAULT_CONFIG = {
    "timeout": 4000,
    "show_notifications": "all",
    "show_only_when_unfocused": True,

    "titlepattern": "<artist|<artist> - ><title>",
    "bodypattern":
"""<~length>
<album|<album><discsubtitle| - <discsubtitle>>
><~year|<~year>>""",
}


def get_conf_value(name, accessor="get"):
    try:
        value = getattr(config, accessor)("plugins", "notify_%s" % name)
    except Exception:
        value = DEFAULT_CONFIG[name]
    return value

get_conf_bool = lambda name: get_conf_value(name, "getboolean")
get_conf_int = lambda name: get_conf_value(name, "getint")


def set_conf_value(name, value):
    config.set("plugins", "notify_%s" % name, unicode(value))


class PreferencesWidget(Gtk.VBox):
    def __init__(self, parent, plugin_instance):
        GObject.GObject.__init__(self, spacing=12)
        self.plugin_instance = plugin_instance

        # notification text settings
        table = Gtk.Table(2, 3)
        table.set_col_spacings(6)
        table.set_row_spacings(6)

        text_frame = qltk.Frame(_("Notification text"), child=table)

        title_entry = UndoEntry()
        title_entry.set_text(get_conf_value("titlepattern"))
        title_entry.connect("focus-out-event", self.on_entry_unfocused,
                            "titlepattern")
        table.attach(title_entry, 1, 2, 0, 1)

        title_label = Gtk.Label(label=_("_Title:"))
        title_label.set_use_underline(True)
        title_label.set_alignment(0, 0.5)
        title_label.set_mnemonic_widget(title_entry)
        table.attach(title_label, 0, 1, 0, 1,
                     xoptions=Gtk.AttachOptions.FILL |
                     Gtk.AttachOptions.SHRINK)

        title_revert = Gtk.Button()
        title_revert.add(Gtk.Image.new_from_stock(
            Gtk.STOCK_REVERT_TO_SAVED, Gtk.IconSize.MENU))
        title_revert.set_tooltip_text(_("Revert to default pattern"))
        title_revert.connect_object(
            "clicked", title_entry.set_text, DEFAULT_CONFIG["titlepattern"])
        table.attach(title_revert, 2, 3, 0, 1,
                     xoptions=Gtk.AttachOptions.SHRINK)

        body_textbuffer = TextBuffer()
        body_textview = TextView(buffer=body_textbuffer)
        body_textview.set_size_request(-1, 85)
        body_textview.get_buffer().set_text(get_conf_value("bodypattern"))
        body_textview.connect("focus-out-event", self.on_textview_unfocused,
                              "bodypattern")
        body_scrollarea = Gtk.ScrolledWindow()
        body_scrollarea.set_policy(Gtk.PolicyType.AUTOMATIC,
                                   Gtk.PolicyType.AUTOMATIC)
        body_scrollarea.set_shadow_type(Gtk.ShadowType.ETCHED_OUT)
        body_scrollarea.add(body_textview)
        table.attach(body_scrollarea, 1, 2, 1, 2)

        body_label = Gtk.Label(label=_("_Body:"))
        body_label.set_padding(0, 3)
        body_label.set_use_underline(True)
        body_label.set_alignment(0, 0)
        body_label.set_mnemonic_widget(body_textview)
        table.attach(body_label, 0, 1, 1, 2, xoptions=Gtk.AttachOptions.SHRINK)

        revert_align = Gtk.Alignment()
        body_revert = Gtk.Button()
        body_revert.add(Gtk.Image.new_from_stock(
                        Gtk.STOCK_REVERT_TO_SAVED, Gtk.IconSize.MENU))
        body_revert.set_tooltip_text(_("Revert to default pattern"))
        body_revert.connect_object(
            "clicked", body_textbuffer.set_text, DEFAULT_CONFIG["bodypattern"])
        revert_align.add(body_revert)
        table.attach(
            revert_align, 2, 3, 1, 2,
            xoptions=Gtk.AttachOptions.SHRINK,
            yoptions=Gtk.AttachOptions.FILL | Gtk.AttachOptions.SHRINK)

        # preview button
        preview_button = qltk.Button(
            _("_Show notification"), Gtk.STOCK_EXECUTE)
        preview_button.set_sensitive(app.player.info is not None)
        preview_button.connect("clicked", self.on_preview_button_clicked)
        self.qlplayer_connected_signals = [
            app.player.connect("paused", self.on_player_state_changed,
                             preview_button),
            app.player.connect("unpaused", self.on_player_state_changed,
                             preview_button),
        ]

        table.attach(
            preview_button, 0, 3, 2, 3,
            xoptions=Gtk.AttachOptions.FILL | Gtk.AttachOptions.SHRINK)

        self.pack_start(text_frame, True, True, 0)

        # notification display settings
        display_box = Gtk.VBox(spacing=12)
        display_frame = qltk.Frame(_("Show notifications"), child=display_box)

        radio_box = Gtk.VBox(spacing=6)
        display_box.pack_start(radio_box, True, True, 0)

        only_user_radio = Gtk.RadioButton(label=_(
            "Only on <i>_manual</i> song changes"
        ), use_underline=True)
        only_user_radio.get_child().set_use_markup(True)
        only_user_radio.connect("toggled", self.on_radiobutton_toggled,
                                "show_notifications", "user")
        radio_box.pack_start(only_user_radio, True, True, 0)

        only_auto_radio = Gtk.RadioButton(group=only_user_radio, label=_(
            "Only on <i>_automatic</i> song changes"
        ), use_underline=True)
        only_auto_radio.get_child().set_use_markup(True)
        only_auto_radio.connect("toggled", self.on_radiobutton_toggled,
                                "show_notifications", "auto")
        radio_box.pack_start(only_auto_radio, True, True, 0)

        all_radio = Gtk.RadioButton(group=only_user_radio, label=_(
            "On <i>a_ll</i> song changes"
        ), use_underline=True)
        all_radio.get_child().set_use_markup(True)
        all_radio.connect("toggled", self.on_radiobutton_toggled,
                          "show_notifications", "all")
        radio_box.pack_start(all_radio, True, True, 0)

        try:
            {
                "user": only_user_radio,
                "auto": only_auto_radio,
                "all": all_radio
            }[get_conf_value("show_notifications")].set_active(True)
        except KeyError:
            all_radio.set_active(True)
            set_conf_value("show_notifications", "all")

        focus_check = Gtk.CheckButton(_("Only when the main window is not "
                                        "_focused"))
        focus_check.set_active(get_conf_bool("show_only_when_unfocused"))
        focus_check.connect("toggled", self.on_checkbutton_toggled,
                            "show_only_when_unfocused")
        display_box.pack_start(focus_check, True, True, 0)

        self.pack_start(display_frame, True, True, 0)

        self.show_all()
        self.connect("destroy", self.on_destroyed)

    # callbacks
    def on_entry_unfocused(self, entry, event, cfgname):
        set_conf_value(cfgname, entry.get_text())

    def on_textview_unfocused(self, textview, event, cfgname):
        text_buffer = textview.get_buffer()
        start, end = text_buffer.get_bounds()
        text = text_buffer.get_text(start, end, True)
        set_conf_value(cfgname, text)

    def on_radiobutton_toggled(self, radio, cfgname, value):
        if radio.get_active():
            set_conf_value(cfgname, value)

    def on_checkbutton_toggled(self, button, cfgname):
        set_conf_value(cfgname, button.get_active())

    def on_preview_button_clicked(self, button):
        if app.player.info is not None:
            if not self.plugin_instance.show_notification(app.player.info):
                ErrorMessage(self, _("Connection Error"),
                    _("Couldn't connect to notification daemon.")).run()

    def on_player_state_changed(self, player, preview_button):
        preview_button.set_sensitive(player.info is not None)

    def on_destroyed(self, ev):
        for sig in self.qlplayer_connected_signals:
            app.player.disconnect(sig)
        self.qlplayer_connected_signals = []
        self.plugin_instance = None


class Notify(EventPlugin):
    PLUGIN_ID = "Notify"
    PLUGIN_NAME = _("Song Notifications")
    PLUGIN_DESC = _("Display a notification when the song changes.")
    PLUGIN_ICON = Gtk.STOCK_DIALOG_INFO
    PLUGIN_VERSION = "1.1"

    DBUS_NAME = "org.freedesktop.Notifications"
    DBUS_IFACE = "org.freedesktop.Notifications"
    DBUS_PATH = "/org/freedesktop/Notifications"

    # these can all be used even if it wasn't enabled
    __enabled = False
    __last_id = 0
    __image_fp = None
    __interface = None
    __action_sig = None
    __watch = None

    def enabled(self):
        self.__enabled = True

        # This works because:
        #  - if paused, any on_song_started event will be generated by user
        #    interaction
        #  - if playing, an on_song_ended event will be generated before any
        #    on_song_started event in any case.
        self.__was_stopped_by_user = True

        self.__force_notification = False
        self.__caps = None
        self.__spec_version = None

        self.__enable_watch()

    def disabled(self):
        self.__disable_watch()
        self.__disconnect()
        self.__enabled = False
        self.__image_fp = None

    def __enable_watch(self):
        """Enable events for dbus name owner change"""
        try:
            bus = dbus.Bus(dbus.Bus.TYPE_SESSION)
            # This also triggers for existing name owners
            self.__watch = bus.watch_name_owner(self.DBUS_NAME,
                                                self.__owner_changed)
        except dbus.DBusException:
            pass

    def __disable_watch(self):
        """Disable name owner change events"""
        if self.__watch:
            self.__watch.cancel()
            self.__watch = None

    def __disconnect(self):
        self.__interface = None
        if self.__action_sig:
            self.__action_sig.remove()
            self.__action_sig = None

    def __owner_changed(self, owner):
        # In case the owner gets removed, remove all references to it
        if not owner:
            self.__disconnect()

    def PluginPreferences(self, parent):
        return PreferencesWidget(parent, self)

    def __get_interface(self):
        """Returns a fresh proxy + info about the server"""

        obj = dbus.SessionBus().get_object(self.DBUS_NAME, self.DBUS_PATH)
        interface = dbus.Interface(obj, self.DBUS_IFACE)

        name, vendor, version, spec_version = \
            map(str, interface.GetServerInformation())
        spec_version = map(int, spec_version.split("."))
        caps = map(str, interface.GetCapabilities())

        return interface, caps, spec_version

    def close_notification(self):
        """Closes the last opened notification"""

        if not self.__last_id:
            return

        try:
            obj = dbus.SessionBus().get_object(self.DBUS_NAME, self.DBUS_PATH)
            interface = dbus.Interface(obj, self.DBUS_IFACE)
            interface.CloseNotification(self.__last_id)
        except dbus.DBusException:
            pass
        else:
            self.__last_id = 0

    def show_notification(self, song):
        """Returns True if showing the notification was successful"""

        if not song:
            return True

        try:
            if self.__enabled:
                # we are enabled try to work with the data we have and
                # keep it fresh
                if not self.__interface:
                    iface, caps, spec = self.__get_interface()
                    self.__interface = iface
                    self.__caps = caps
                    self.__spec_version = spec
                    if "actions" in caps:
                        self.__action_sig = iface.connect_to_signal(
                            "ActionInvoked", self.on_dbus_action)
                else:
                    iface = self.__interface
                    caps = self.__caps
                    spec = self.__spec_version
            else:
                # not enabled, just get everything temporary,
                # propably preview
                iface, caps, spec = self.__get_interface()

        except dbus.DBusException:
            print_w("[notify] %s" %
                    _("Couldn't connect to notification daemon."))
            self.__disconnect()
            return False

        strip_markup = lambda t: re.subn("\</?[iub]\>", "", t)[0]
        strip_links = lambda t: re.subn("\</?a.*?\>", "", t)[0]
        strip_images = lambda t: re.subn("\<img.*?\>", "", t)[0]

        title = XMLFromPattern(get_conf_value("titlepattern")) % song
        title = unescape(strip_markup(strip_links(strip_images(title))))

        body = ""
        if "body" in caps:
            body = XMLFromPattern(get_conf_value("bodypattern")) % song

            if "body-markup" not in caps:
                body = strip_markup(body)
            if "body-hyperlinks" not in caps:
                body = strip_links(body)
            if "body-images" not in caps:
                body = strip_images(body)

        image_path = ""
        if "icon-static" in caps:
            self.__image_fp = song.find_cover()
            if self.__image_fp:
                image_path = self.__image_fp.name

        is_temp = image_path.startswith(tempfile.gettempdir())

        # If it is not an embeded cover, drop the file handle
        if not is_temp:
            self.__image_fp = None

        # spec recommends it, and it seems to work
        if image_path and spec >= (1, 1):
            image_path = URI.frompath(image_path)

        actions = []
        if "actions" in caps:
            actions = ["next", _("Next")]

        hints = {
            "desktop-entry": "quodlibet",
        }

        try:
            self.__last_id = iface.Notify(
                "Quod Libet", self.__last_id,
                image_path, title, body, actions, hints,
                get_conf_int("timeout"))
        except dbus.DBusException:
            print_w("[notify] %s" %
                    _("Couldn't connect to notification daemon."))
            self.__disconnect()
            return False

        # preview done, remove all references again
        if not self.__enabled:
            self.__disconnect()

        return True

    def on_dbus_action(self, notify_id, key):
        if notify_id == self.__last_id and key == "next":
            # Always show a new notification if the next button got clicked
            self.__force_notification = True
            app.player.next()

    def on_song_change(self, song, typ):
        if not song:
            self.close_notification()
        if get_conf_value("show_notifications") in [typ, "all"] \
                and not (get_conf_bool("show_only_when_unfocused")
                         and app.window.has_toplevel_focus()) \
                or self.__force_notification:
            def idle_show(song):
                self.show_notification(song)
            GLib.idle_add(idle_show, song)
            self.__force_notification = False

    def plugin_on_song_started(self, song):
        typ = (self.__was_stopped_by_user and "user") or "auto"
        self.on_song_change(song, typ)

    def plugin_on_song_ended(self, song, stopped):
        # if `stopped` is `True`, this song was ended due to some kind of user
        # interaction.
        self.__was_stopped_by_user = stopped
