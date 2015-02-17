# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import unicodedata

from gi.repository import Gtk, Gdk

from quodlibet import const
from quodlibet import qltk
from quodlibet import util

from quodlibet.plugins import PluginManager
from quodlibet.pattern import FileFromPattern
from quodlibet.qltk._editutils import FilterPluginBox, FilterCheckButton
from quodlibet.qltk._editutils import EditingPluginHandler
from quodlibet.qltk.views import TreeViewColumn
from quodlibet.qltk.cbes import ComboBoxEntrySave
from quodlibet.qltk.models import ObjectStore
from quodlibet.qltk.wlw import WritingWindow
from quodlibet.util import connect_obj
from quodlibet.util.path import fsdecode, fsnative
from quodlibet.util.path import strip_win32_incompat_from_path


class SpacesToUnderscores(FilterCheckButton):
    _label = _("Replace spaces with _underscores")
    _section = "rename"
    _key = "spaces"
    _order = 1.0

    def filter(self, original, filename):
        return filename.replace(" ", "_")


class StripWindowsIncompat(FilterCheckButton):
    _label = _("Strip _Windows-incompatible characters")
    _section = "rename"
    _key = "windows"
    _order = 1.1

    def __init__(self):
        super(StripWindowsIncompat, self).__init__()
        # If on Windows, force this to be inactive (and hidden)
        if os.name == 'nt':
            self.set_active(False)
            self.set_sensitive(False)
            self.set_no_show_all(True)

    def filter(self, original, filename):
        return strip_win32_incompat_from_path(filename)


class StripDiacriticals(FilterCheckButton):
    _label = _("Strip _diacritical marks")
    _section = "rename"
    _key = "diacriticals"
    _order = 1.2

    def filter(self, original, filename):
        filename = fsdecode(filename)
        return fsnative(filter(lambda s: not unicodedata.combining(s),
                               unicodedata.normalize('NFKD', filename)))


class StripNonASCII(FilterCheckButton):
    _label = _("Strip non-_ASCII characters")
    _section = "rename"
    _key = "ascii"
    _order = 1.3

    def filter(self, original, filename):
        filename = fsdecode(filename)
        return fsnative(
            u"".join(map(lambda s: (s <= "~" and s) or u"_", filename)))


class Lowercase(FilterCheckButton):
    _label = _("Use only _lowercase characters")
    _section = "rename"
    _key = "lowercase"
    _order = 1.4

    def filter(self, original, filename):
        return filename.lower()


class RenameFilesPluginHandler(EditingPluginHandler):
    from quodlibet.plugins.editing import RenameFilesPlugin
    Kind = RenameFilesPlugin


class Entry(object):

    def __init__(self, song):
        self.song = song

    new_name = None
    """new name as unicode or None if not set"""

    @property
    def name(self):
        return fsdecode(self.song("~basename"))


class RenameFiles(Gtk.VBox):
    title = _("Rename Files")
    FILTERS = [SpacesToUnderscores, StripWindowsIncompat, StripDiacriticals,
               StripNonASCII, Lowercase]
    handler = RenameFilesPluginHandler()

    @classmethod
    def init_plugins(cls):
        PluginManager.instance.register_handler(cls.handler)

    def __init__(self, parent, library):
        super(RenameFiles, self).__init__(spacing=6)
        self.set_border_width(12)

        hbox = Gtk.HBox(spacing=6)
        cbes_defaults = const.NBP_EXAMPLES.split("\n")
        self.combo = ComboBoxEntrySave(const.NBP, cbes_defaults,
            title=_("Path Patterns"),
            edit_title=_(u"Edit saved patterns…"))
        self.combo.show_all()
        hbox.pack_start(self.combo, True, True, 0)
        self.preview = qltk.Button(_("_Preview"), Gtk.STOCK_CONVERT)
        self.preview.show()
        hbox.pack_start(self.preview, False, True, 0)
        self.pack_start(hbox, False, True, 0)
        self.combo.get_child().connect('changed', self._changed)

        model = ObjectStore()
        self.view = Gtk.TreeView(model=model)
        self.view.show()

        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.view)
        self.pack_start(sw, True, True, 0)

        self.pack_start(Gtk.VBox(), False, True, 0)

        filter_box = FilterPluginBox(self.handler, self.FILTERS)
        filter_box.connect("preview", self.__filter_preview)
        filter_box.connect("changed", self.__filter_changed)
        self.filter_box = filter_box
        self.pack_start(filter_box, False, True, 0)

        # Save button
        self.save = Gtk.Button(stock=Gtk.STOCK_SAVE)
        self.save.show()
        bbox = Gtk.HButtonBox()
        bbox.set_layout(Gtk.ButtonBoxStyle.END)
        bbox.pack_start(self.save, True, True, 0)
        self.pack_start(bbox, False, True, 0)

        render = Gtk.CellRendererText()
        column = TreeViewColumn(_('File'), render)

        def cell_data_file(column, cell, model, iter_, data):
            entry = model.get_value(iter_)
            cell.set_property("text", entry.name)

        column.set_cell_data_func(render, cell_data_file)

        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.view.append_column(column)

        render = Gtk.CellRendererText()
        render.set_property('editable', True)
        column = TreeViewColumn(_('New Name'), render)

        def cell_data_new_name(column, cell, model, iter_, data):
            entry = model.get_value(iter_)
            cell.set_property("text", entry.new_name or u"")
        column.set_cell_data_func(render, cell_data_new_name)

        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.view.append_column(column)

        connect_obj(self.preview, 'clicked', self.__preview, None)

        connect_obj(parent, 'changed', self.__class__.__preview, self)
        connect_obj(self.save, 'clicked', self.__rename, library)

        render.connect('edited', self.__row_edited)

        for child in self.get_children():
            child.show()

    def __filter_preview(self, *args):
        Gtk.Button.clicked(self.preview)

    def __filter_changed(self, *args):
        self._changed(self.combo.get_child())

    def _changed(self, entry):
        self.save.set_sensitive(False)
        self.preview.set_sensitive(bool(entry.get_text()))

    def __row_edited(self, renderer, path, new):
        path = Gtk.TreePath.new_from_string(path)
        model = self.view.get_model()
        entry = model[path][0]
        new = new.decode("utf-8")
        if entry.new_name != new:
            entry.new_name = new
            self.preview.set_sensitive(True)
            self.save.set_sensitive(True)
            model.path_changed(path)

    def __rename(self, library):
        model = self.view.get_model()
        win = WritingWindow(self, len(model))
        win.show()
        was_changed = set()
        skip_all = False
        self.view.freeze_child_notify()

        for entry in model.itervalues():
            song = entry.song
            new_name = entry.new_name
            old_name = entry.name
            if new_name is None:
                continue

            try:
                library.rename(song, fsnative(new_name), changed=was_changed)
            except Exception:
                util.print_exc()
                if skip_all:
                    continue
                RESPONSE_SKIP_ALL = 1
                buttons = (_("Ignore _All Errors"), RESPONSE_SKIP_ALL,
                           Gtk.STOCK_STOP, Gtk.ResponseType.CANCEL,
                           _("_Continue"), Gtk.ResponseType.OK)
                msg = qltk.Message(
                    Gtk.MessageType.ERROR, win, _("Unable to rename file"),
                    _("Renaming <b>%(old-name)s</b> to <b>%(new-name)s</b> "
                      "failed. Possibly the target file already exists, "
                      "or you do not have permission to make the "
                      "new file or remove the old one.") % {
                        "old-name": util.escape(old_name),
                        "new-name": util.escape(new_name),
                      },
                    buttons=Gtk.ButtonsType.NONE)
                msg.add_buttons(*buttons)
                msg.set_default_response(Gtk.ResponseType.OK)
                resp = msg.run()
                skip_all |= (resp == RESPONSE_SKIP_ALL)
                # Preserve old behavior: shift-click is Ignore All
                mods = Gdk.Display.get_default().get_pointer()[3]
                skip_all |= mods & Gdk.ModifierType.SHIFT_MASK
                library.reload(song, changed=was_changed)
                if resp != Gtk.ResponseType.OK and resp != RESPONSE_SKIP_ALL:
                    break
            if win.step():
                break

        self.view.thaw_child_notify()
        win.destroy()
        library.changed(was_changed)
        self.save.set_sensitive(False)

    def __preview(self, songs):
        model = self.view.get_model()
        if songs is None:
            songs = [e.song for e in model.itervalues()]

        pattern_text = self.combo.get_child().get_text().decode("utf-8")

        try:
            pattern = FileFromPattern(pattern_text)
        except ValueError:
            qltk.ErrorMessage(
                self, _("Path is not absolute"),
                _("The pattern\n\t<b>%s</b>\ncontains / but "
                  "does not start from root. To avoid misnamed "
                  "folders, root your pattern by starting "
                  "it with / or ~/.") % (
                util.escape(pattern))).run()
            return
        else:
            if pattern:
                self.combo.prepend_text(pattern_text)
                self.combo.write(const.NBP)

        # native paths
        orignames = [song["~filename"] for song in songs]
        newnames = [pattern.format(song) for song in songs]
        for f in self.filter_box.filters:
            if f.active:
                newnames = f.filter_list(orignames, newnames)

        model.clear()
        for song, newname in zip(songs, newnames):
            entry = Entry(song)
            entry.new_name = fsdecode(newname)
            model.append(row=[entry])

        self.preview.set_sensitive(False)
        self.save.set_sensitive(bool(pattern_text))
        for song in songs:
            if not song.is_file:
                self.set_sensitive(False)
                break
        else:
            self.set_sensitive(True)
