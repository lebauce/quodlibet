# -*- coding: utf-8 -*-
# Copyright 2006 Markus Koller
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

from gi.repository import Gtk, Pango

from quodlibet import config
from quodlibet import devices
from quodlibet import qltk
from quodlibet import util

from quodlibet.browsers._base import Browser
from quodlibet.formats._audio import AudioFile
from quodlibet.qltk.views import AllTreeView
from quodlibet.qltk.songsmenu import SongsMenu
from quodlibet.qltk.wlw import WaitLoadBar
from quodlibet.qltk.browser import LibraryBrowser
from quodlibet.qltk.delete import DeleteDialog
from quodlibet.qltk.x import Alignment, ScrolledWindow, Button


class DeviceProperties(Gtk.Dialog):
    def __init__(self, parent, device):
        super(DeviceProperties, self).__init__(
            title=_("Device Properties"),
            transient_for=qltk.get_top_parent(parent))

        self.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(400, -1)
        self.connect('response', self.__close)

        table = Gtk.Table()
        table.set_border_width(8)
        table.set_row_spacings(8)
        table.set_col_spacings(8)
        self.vbox.pack_start(table, False, True, 0)

        props = []

        props.append((_("Device:"), device.dev, None))
        mountpoint = util.escape(
            device.mountpoint or ("<i>%s</i>" % _("Not mounted")))
        props.append((_("Mount Point:"), mountpoint, None))

        props.append((None, None, None))

        entry = Gtk.Entry()
        entry.set_text(device['name'])
        props.append((_("_Name:"), entry, 'name'))

        y = 0
        for title, value, key in props + device.Properties():
            if title is None:
                table.attach(Gtk.HSeparator(), 0, 2, y, y + 1)
            else:
                if key and isinstance(value, Gtk.CheckButton):
                    value.set_label(title)
                    value.set_use_underline(True)
                    value.connect('toggled', self.__changed, key, device)
                    table.attach(value, 0, 2, y, y + 1,
                                 xoptions=Gtk.AttachOptions.FILL)
                else:
                    label = Gtk.Label()
                    label.set_markup("<b>%s</b>" % util.escape(title))
                    label.set_alignment(0.0, 0.5)
                    table.attach(label, 0, 1, y, y + 1,
                                 xoptions=Gtk.AttachOptions.FILL)
                    if key and isinstance(value, Gtk.Widget):
                        widget = value
                        label.set_mnemonic_widget(widget)
                        label.set_use_underline(True)
                        widget.connect('changed', self.__changed, key, device)
                    else:
                        widget = Gtk.Label(label=value)
                        widget.set_use_markup(True)
                        widget.set_selectable(True)
                        widget.set_alignment(0.0, 0.5)
                    table.attach(widget, 1, 2, y, y + 1)
            y += 1
        self.get_child().show_all()

    def __changed(self, widget, key, device):
        if isinstance(widget, Gtk.Entry):
            value = widget.get_text()
        elif isinstance(widget, Gtk.SpinButton):
            value = widget.get_value()
        elif isinstance(widget, Gtk.CheckButton):
            value = widget.get_active()
        else:
            raise NotImplementedError
        device[key] = value

    def __close(self, dialog, response):
        dialog.destroy()
        devices.write()


# This will be included in SongsMenu
class Menu(Gtk.Menu):
    def __init__(self, songs, library):
        super(Menu, self).__init__()
        for device in MediaDevices.devices():
            i = Gtk.ImageMenuItem(device['name'])
            i.set_image(
                Gtk.Image.new_from_icon_name(device.icon, Gtk.IconSize.MENU))
            i.set_sensitive(device.is_connected())
            i.connect_object(
                'activate', self.__copy_to_device, device, songs, library)
            self.append(i)

    @staticmethod
    def __copy_to_device(device, songs, library):
        if len(MediaDevices.instances()) > 0:
            browser = MediaDevices.instances()[0]
        else:
            win = LibraryBrowser.open(MediaDevices, library)
            browser = win.browser
        browser.select(device)
        browser.dropped(browser.get_toplevel().songlist, songs)


class MediaDevices(Gtk.VBox, Browser, util.InstanceTracker):
    __gsignals__ = Browser.__gsignals__

    name = _("Media Devices")
    accelerated_name = _("_Media Devices")
    priority = 25
    replaygain_profiles = ['track']

    __devices = Gtk.ListStore(object, str)
    __busy = False
    __last = None

    @staticmethod
    def cell_data(col, render, model, iter, data):
        device = model[iter][0]
        if device.is_connected():
            render.markup = "<b>%s</b>" % util.escape(device['name'])
        else:
            render.markup = util.escape(device['name'])
        render.set_property('markup', render.markup)

    @classmethod
    def init(klass, library):
        devices.device_manager.connect('added', klass.__device_added)
        devices.device_manager.connect('removed', klass.__device_removed)
        devices.device_manager.discover()

    @classmethod
    def devices(klass):
        return [row[0] for row in klass.__devices]

    @classmethod
    def __device_added(klass, manager, device):
        klass.__devices.append(row=[device, device.icon])

    @classmethod
    def __device_removed(klass, manager, bid):
        for row in klass.__devices:
            if row[0].bid == bid:
                klass.__devices.remove(row.iter)
                break

    def __init__(self, library, main):
        super(MediaDevices, self).__init__(spacing=6)
        self._register_instance()

        self.__cache = {}

        # Device list on the left pane
        swin = ScrolledWindow()
        swin.set_shadow_type(Gtk.ShadowType.IN)
        swin.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(swin, True, True, 0)

        self.__view = view = AllTreeView()
        view.set_model(self.__devices)
        view.set_rules_hint(True)
        view.set_headers_visible(False)
        view.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
        view.get_selection().connect_object('changed', self.__refresh, False)
        view.connect('popup-menu', self.__popup_menu, library)
        if main:
            view.connect('row-activated', lambda *a: self.emit("activated"))
        swin.add(view)

        col = Gtk.TreeViewColumn("Devices")
        view.append_column(col)

        render = Gtk.CellRendererPixbuf()
        col.pack_start(render, False)
        col.add_attribute(render, 'icon-name', 1)

        self.__render = render = Gtk.CellRendererText()
        render.set_property('ellipsize', Pango.EllipsizeMode.END)
        render.connect('edited', self.__edited)
        col.pack_start(render, True)
        col.set_cell_data_func(render, MediaDevices.cell_data)

        hbox = Gtk.HBox(spacing=6)
        hbox.set_homogeneous(True)
        if main:
            self.pack_start(Alignment(hbox, left=3, bottom=3), False, True, 0)
        else:
            self.pack_start(hbox, False, True, 0)

        # refresh button
        refresh = Button(_("_Refresh"), Gtk.STOCK_REFRESH, Gtk.IconSize.MENU)
        self.__refresh_button = refresh
        refresh.connect_object('clicked', self.__refresh, True)
        refresh.set_sensitive(False)
        hbox.pack_start(refresh, True, True, 0)

        # eject button
        eject = Button(_("_Eject"), "media-eject", Gtk.IconSize.MENU)
        self.__eject_button = eject
        eject.connect('clicked', self.__eject)
        eject.set_sensitive(False)
        hbox.pack_start(eject, True, True, 0)

        # Device info on the right pane
        self.__header = table = Gtk.Table()
        table.set_col_spacings(8)

        self.__device_icon = icon = Gtk.Image()
        icon.set_size_request(48, 48)
        table.attach(icon, 0, 1, 0, 2, 0)

        self.__device_name = label = Gtk.Label()
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_alignment(0, 0)
        table.attach(label, 1, 3, 0, 1)

        self.__device_space = label = Gtk.Label()
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_alignment(0, 0.5)
        table.attach(label, 1, 2, 1, 2)

        self.__progress = progress = Gtk.ProgressBar()
        progress.set_size_request(150, -1)
        table.attach(progress, 2, 3, 1, 2, xoptions=0, yoptions=0)

        self.accelerators = Gtk.AccelGroup()
        key, mod = Gtk.accelerator_parse('F2')
        self.accelerators.connect(key, mod, 0, self.__rename)

        self.__statusbar = WaitLoadBar()

        for child in self.get_children():
            child.show_all()

    def pack(self, songpane):
        self.__vbox = vbox = Gtk.VBox(spacing=6)
        vbox.pack_start(self.__header, False, True, 0)
        vbox.pack_start(songpane, True, True, 0)
        vbox.pack_start(self.__statusbar, False, True, 0)

        vbox.show()
        self.__header.show_all()
        self.__header.hide()
        self.__statusbar.show_all()
        self.__statusbar.hide()
        self.show()

        self.__paned = paned = qltk.RHPaned()
        paned.pack1(self, True, False)
        paned.pack2(vbox, True, False)
        return paned

    def unpack(self, container, songpane):
        self.__vbox.remove(songpane)
        self.__paned.remove(self)

    def Menu(self, songs, songlist, library):
        model, iter = self.__view.get_selection().get_selected()
        if iter:
            device = model[iter][0]
            delete = device.delete and self.__delete_songs
        else:
            delete = False

        menu = SongsMenu(library, songs, delete=delete, remove=False,
                         parent=self)
        return menu

    def activate(self):
        self.__refresh()

    def save(self):
        selection = self.__view.get_selection()
        model, iter = selection.get_selected()
        if iter:
            config.set('browsers', 'media', model[iter][0]['name'])

    def restore(self):
        try:
            name = config.get('browsers', 'media')
        except config.Error:
            pass
        else:
            for row in self.__devices:
                if row[0]['name'] == name:
                    break
            else:
                return
            selection = self.__view.get_selection()
            selection.unselect_all()
            selection.select_iter(row.iter)

    def select(self, device):
        for row in self.__devices:
            if row[0] == device:
                break
        else:
            return

        # Force a full refresh
        try:
            del self.__cache[device.bid]
        except KeyError:
            pass

        selection = self.__view.get_selection()
        selection.unselect_all()
        selection.select_iter(row.iter)

    def dropped(self, songlist, songs):
        return self.__copy_songs(songlist, songs)

    def __popup_menu(self, view, library):
        model, iter = view.get_selection().get_selected()
        device = model[iter][0]

        if device.is_connected() and not self.__busy:
            songs = self.__list_songs(device)
        else:
            songs = []
        menu = SongsMenu(library, songs, playlists=False,
                         devices=False, remove=False, parent=self)

        menu.preseparate()

        props = Gtk.ImageMenuItem(Gtk.STOCK_PROPERTIES, use_stock=True)
        props.connect_object('activate', self.__properties, model[iter][0])
        props.set_sensitive(not self.__busy)
        menu.prepend(props)

        ren = qltk.MenuItem(_("_Rename"), Gtk.STOCK_EDIT)
        keyval, mod = Gtk.accelerator_parse("F2")
        ren.add_accelerator(
            'activate', self.accelerators, keyval, mod, Gtk.AccelFlags.VISIBLE)

        def rename(path):
            self.__render.set_property('editable', True)
            view.set_cursor(path, view.get_columns()[0], start_editing=True)
        ren.connect_object('activate', rename, model.get_path(iter))
        menu.prepend(ren)

        menu.preseparate()

        eject = Gtk.ImageMenuItem(_("_Eject"), use_underline=True)
        eject.set_image(
            Gtk.Image.new_from_icon_name("media-eject", Gtk.IconSize.MENU))
        eject.set_sensitive(
            not self.__busy and device.eject and device.is_connected())
        eject.connect_object('activate', self.__eject, None)
        menu.prepend(eject)

        refresh = Gtk.ImageMenuItem(Gtk.STOCK_REFRESH, use_stock=True)
        refresh.set_sensitive(device.is_connected())
        refresh.connect_object('activate', self.__refresh, True)
        menu.prepend(refresh)

        menu.show_all()
        return view.popup_menu(menu, 0, Gtk.get_current_event_time())

    def __properties(self, device):
        DeviceProperties(self, device).run()
        self.__set_name(device)

    def __rename(self, group, acceleratable, keyval, modifier):
        model, iter = self.__view.get_selection().get_selected()
        if iter:
            self.__render.set_property('editable', True)
            self.__view.set_cursor(model.get_path(iter),
                                   self.__view.get_columns()[0],
                                   start_editing=True)

    def __edited(self, render, path, newname):
        self.__devices[path][0]['name'] = newname
        self.__set_name(self.__devices[path][0])
        render.set_property('editable', False)
        devices.write()

    def __set_name(self, device):
        self.__device_name.set_markup(
            '<span size="x-large"><b>%s</b></span>' %
            util.escape(device['name']))

    def __refresh(self, rescan=False):
        model, iter = self.__view.get_selection().get_selected()
        if iter:
            path = model[iter].path
            if not rescan and self.__last == path:
                return
            self.__last = path

            device = model[iter][0]
            self.__device_icon.set_from_icon_name(
                device.icon, Gtk.IconSize.DIALOG)
            self.__set_name(device)

            songs = []
            if device.is_connected():
                self.__header.show_all()
                self.__eject_button.set_sensitive(bool(device.eject))
                self.__refresh_button.set_sensitive(True)
                self.__refresh_space(device)

                try:
                    songs = self.__list_songs(device, rescan)
                except NotImplementedError:
                    pass
            else:
                self.__eject_button.set_sensitive(False)
                self.__refresh_button.set_sensitive(False)
                self.__header.hide()
            self.emit('songs-selected', songs, device.ordered)
        else:
            self.__last = None
            self.emit('songs-selected', [], False)

    def __refresh_space(self, device):
        try:
            space, free = device.get_space()
        except NotImplementedError:
            self.__device_space.set_text("")
            self.__progress.hide()
        else:
            used = space - free
            fraction = float(used) / space

            self.__device_space.set_markup(
                _("<b>%s</b> used, <b>%s</b> available") %
                (util.format_size(used), util.format_size(free)))
            self.__progress.set_fraction(fraction)
            self.__progress.set_text("%.f%%" % round(fraction * 100))
            self.__progress.show()

    def __list_songs(self, device, rescan=False):
        if rescan or not device.bid in self.__cache:
            self.__busy = True
            self.__cache[device.bid] = device.list(self.__statusbar)
            self.__busy = False
        return self.__cache[device.bid]

    def __check_device(self, device, message):
        if not device.is_connected():
            qltk.WarningMessage(
                self, message,
                _("<b>%s</b> is not connected.") % util.escape(device['name'])
            ).run()
            return False
        return True

    def __copy_songs(self, songlist, songs):
        model, iter = self.__view.get_selection().get_selected()
        if not iter:
            return False

        device = model[iter][0]
        if not self.__check_device(device, _("Unable to copy songs")):
            return False

        self.__busy = True

        wlb = self.__statusbar
        wlb.setup(len(songs), _("Copying <b>%(song)s</b>"), {'song': ''})
        wlb.show()

        model = songlist.get_model()
        for song in songs:
            label = util.escape(song('~artist~title'))
            if wlb.step(song=label):
                wlb.hide()
                break

            if len(model) > 0:
                songlist.scroll_to_cell(model[-1].path)
            while Gtk.events_pending():
                Gtk.main_iteration()

            space, free = device.get_space()
            if free < os.path.getsize(song['~filename']):
                wlb.hide()
                qltk.WarningMessage(
                    self, _("Unable to copy song"),
                    _("There is not enough free space for this song.")
                ).run()
                break

            status = device.copy(songlist, song)
            if isinstance(status, AudioFile):
                model.append([status])
                try:
                    self.__cache[device.bid].append(song)
                except KeyError:
                    pass
                self.__refresh_space(device)
            else:
                msg = _("<b>%s</b> could not be copied.") % label
                if type(status) == unicode:
                    msg += "\n\n" + util.escape(status)
                qltk.WarningMessage(self, _("Unable to copy song"), msg).run()

        if device.cleanup and not device.cleanup(wlb, 'copy'):
            pass
        else:
            wlb.hide()

        self.__busy = False
        return True

    def __delete_songs(self, songs):
        model, iter = self.__view.get_selection().get_selected()
        if not iter:
            return False
        songlist = qltk.get_top_parent(self).songlist

        device = model[iter][0]
        if not self.__check_device(device, _("Unable to delete songs")):
            return False

        dialog = DeleteDialog.for_songs(self, songs)
        if dialog.run() != DeleteDialog.RESPONSE_DELETE:
            return False

        self.__busy = True

        wlb = self.__statusbar
        wlb.setup(len(songs), _("Deleting <b>%(song)s</b>"), {'song': ''})
        wlb.show()

        model = songlist.get_model()
        for song in songs:
            label = util.escape(song('~artist~title'))
            if wlb.step(song=label):
                wlb.hide()
                break

            status = device.delete(songlist, song)
            if status is True:
                model.remove(model.find(song))
                try:
                    self.__cache[device.bid].remove(song)
                except (KeyError, ValueError):
                    pass
                self.__refresh_space(device)
            else:
                msg = _("<b>%s</b> could not be deleted.") % label
                if type(status) == unicode:
                    msg += "\n\n%s" % status
                qltk.WarningMessage(
                    self, _("Unable to delete song"), msg).run()

        if device.cleanup and not device.cleanup(wlb, 'delete'):
            pass
        else:
            wlb.hide()

        self.__busy = False

    def __eject(self, button):
        model, iter = self.__view.get_selection().get_selected()
        if iter:
            device = model[iter][0]
            status = device.eject()
            if status is not True:
                msg = _("Ejecting <b>%s</b> failed.") % device['name']
                if status:
                    msg += "\n\n%s" % status
                qltk.ErrorMessage(self, _("Unable to eject device"), msg).run()

if devices.init():
    browsers = [MediaDevices]
else:
    print_w(_("No device backend, Media Devices browser disabled."))
    browsers = []
