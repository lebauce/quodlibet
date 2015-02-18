# -*- coding: utf-8 -*-
# Copyright 2004-2005 Joe Wreschnig, Michael Urman, Iñigo Serna
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os

from gi.repository import Gtk, GObject, Pango

from quodlibet import config
from quodlibet import const
from quodlibet import formats
from quodlibet import qltk

from quodlibet.plugins import PluginManager
from quodlibet.qltk.delete import trash_files, TrashMenuItem
from quodlibet.qltk.edittags import EditTags
from quodlibet.qltk.filesel import MainFileSelector
from quodlibet.qltk.pluginwin import PluginWindow
from quodlibet.qltk.renamefiles import RenameFiles
from quodlibet.qltk.tagsfrompath import TagsFromPath
from quodlibet.qltk.tracknumbers import TrackNumbers
from quodlibet.qltk.entry import UndoEntry
from quodlibet.qltk.about import AboutExFalso
from quodlibet.qltk.songsmenu import SongsMenuPluginHandler
from quodlibet.qltk.x import Alignment, SeparatorMenuItem, ConfigRHPaned, \
    Button
from quodlibet.qltk.window import PersistentWindowMixin, Window, UniqueWindow
from quodlibet.qltk import icons
from quodlibet.util.path import mtime, normalize_path
from quodlibet.util import connect_obj, connect_destroy


class ExFalsoWindow(Window, PersistentWindowMixin):

    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    pm = SongsMenuPluginHandler()

    @classmethod
    def init_plugins(cls):
        PluginManager.instance.register_handler(cls.pm)

    def __init__(self, library, dir=None):
        super(ExFalsoWindow, self).__init__(dialog=False)
        self.set_title("Ex Falso")
        self.set_default_size(750, 475)
        self.enable_window_tracking("exfalso")

        self.__library = library

        hp = ConfigRHPaned("memory", "exfalso_paned_position", 1.0)
        hp.set_border_width(0)
        hp.set_position(250)
        hp.show()
        self.add(hp)

        vb = Gtk.VBox()

        bbox = Gtk.HBox(spacing=6)

        about = Gtk.Button()
        about.add(Gtk.Image.new_from_stock(
            Gtk.STOCK_ABOUT, Gtk.IconSize.BUTTON))
        connect_obj(about, 'clicked', self.__show_about, self)
        bbox.pack_start(about, False, True, 0)

        prefs = Gtk.Button()
        prefs.add(Gtk.Image.new_from_stock(
            Gtk.STOCK_PREFERENCES, Gtk.IconSize.BUTTON))

        def prefs_cb(button):
            window = PreferencesWindow(self)
            window.show()
        prefs.connect('clicked', prefs_cb)
        bbox.pack_start(prefs, False, True, 0)

        plugins = qltk.Button(_("_Plugins"), Gtk.STOCK_EXECUTE)

        def plugin_window_cb(button):
            window = PluginWindow(self)
            window.show()
        plugins.connect('clicked', plugin_window_cb)
        bbox.pack_start(plugins, False, True, 0)

        l = Gtk.Label()
        l.set_alignment(1.0, 0.5)
        l.set_ellipsize(Pango.EllipsizeMode.END)
        bbox.pack_start(l, True, True, 0)

        fs = MainFileSelector()

        vb.pack_start(fs, True, True, 0)
        vb.pack_start(Alignment(bbox, border=6), False, True, 0)
        vb.show_all()

        hp.pack1(vb, resize=True, shrink=False)

        nb = qltk.Notebook()
        nb.props.scrollable = True
        nb.show()
        for Page in [EditTags, TagsFromPath, RenameFiles, TrackNumbers]:
            page = Page(self, self.__library)
            page.show()
            nb.append_page(page)
        align = Alignment(nb, top=3)
        align.show()
        hp.pack2(align, resize=True, shrink=False)
        fs.connect('changed', self.__changed, l)
        if dir:
            fs.go_to(dir)

        connect_destroy(self.__library, 'changed', self.__library_changed, fs)

        self.__save = None
        connect_obj(self, 'changed', self.set_pending, None)
        for c in fs.get_children():
            c.get_child().connect('button-press-event',
                self.__pre_selection_changed, fs, nb)
            c.get_child().connect('focus',
                                  self.__pre_selection_changed, fs, nb)
        fs.get_children()[1].get_child().connect('popup-menu',
                                                 self.__popup_menu, fs)
        self.emit('changed', [])

        self.get_child().show()

        self.__ag = Gtk.AccelGroup()
        key, mod = Gtk.accelerator_parse("<control>Q")
        self.__ag.connect(key, mod, 0, lambda *x: self.destroy())
        self.add_accel_group(self.__ag)

    def __library_changed(self, library, songs, fs):
        fs.rescan()

    def set_as_osx_window(self, osx_app):
        osx_app.set_menu_bar(Gtk.MenuBar())

    def get_osx_is_persistent(self):
        return False

    def __show_about(self, window):
        about = AboutExFalso(self)
        about.run()
        about.destroy()

    def set_pending(self, button, *excess):
        self.__save = button

    def __pre_selection_changed(self, view, event, fs, nb):
        if self.__save:
            resp = qltk.CancelRevertSave(self).run()
            if resp == Gtk.ResponseType.YES:
                self.__save.clicked()
            elif resp == Gtk.ResponseType.NO:
                fs.rescan()
            else:
                nb.grab_focus()
                return True # cancel or closed

    def __popup_menu(self, view, fs):
        # get all songs for the selection
        filenames = [normalize_path(f, canonicalise=True)
                     for f in fs.get_selected_paths()]
        maybe_songs = [self.__library.get(f) for f in filenames]
        songs = [s for s in maybe_songs if s]

        if songs:
            menu = self.pm.Menu(self.__library, self, songs)
            if menu is None:
                menu = Gtk.Menu()
            else:
                menu.prepend(SeparatorMenuItem())
        else:
            menu = Gtk.Menu()

        b = TrashMenuItem()
        b.connect('activate', self.__delete, filenames, fs)
        menu.prepend(b)

        def selection_done_cb(menu):
            menu.destroy()

        menu.connect('selection-done', selection_done_cb)
        menu.show_all()
        return view.popup_menu(menu, 0, Gtk.get_current_event_time())

    def __delete(self, item, paths, fs):
        trash_files(self, paths)
        fs.rescan()

    def __changed(self, selector, selection, label):
        model, rows = selection.get_selected_rows()
        files = []

        if len(rows) < 2:
            count = len(model or [])
        else:
            count = len(rows)
        label.set_text(ngettext("%d song", "%d songs", count) % count)

        for row in rows:
            filename = model[row][0]
            if not os.path.exists(filename):
                pass
            elif filename in self.__library:
                file = self.__library[filename]
                if file("~#mtime") + 1. < mtime(filename):
                    try:
                        file.reload()
                    except StandardError:
                        pass
                files.append(file)
            else:
                files.append(formats.MusicFile(filename))
        files = filter(None, files)
        if len(files) == 0:
            self.set_title("Ex Falso")
        elif len(files) == 1:
            self.set_title("%s - Ex Falso" % files[0].comma("title"))
        else:
            self.set_title(
                "%s - Ex Falso" %
                (ngettext("%(title)s and %(count)d more",
                          "%(title)s and %(count)d more",
                          len(files) - 1) % (
                {'title': files[0].comma("title"), 'count': len(files) - 1})))
        self.__library.add(files)
        self.emit('changed', files)


class PreferencesWindow(UniqueWindow):
    def __init__(self, parent):
        if self.is_not_unique():
            return
        super(PreferencesWindow, self).__init__()
        self.set_title(_("Ex Falso Preferences"))
        self.set_border_width(12)
        self.set_resizable(False)
        self.set_transient_for(parent)

        vbox = Gtk.VBox(spacing=6)
        hb = Gtk.HBox(spacing=6)
        e = UndoEntry()
        e.set_text(config.get("editing", "split_on"))
        e.connect('changed', self.__changed, 'editing', 'split_on')
        l = Gtk.Label(label=_("Split _on:"))
        l.set_use_underline(True)
        l.set_mnemonic_widget(e)
        hb.pack_start(l, False, True, 0)
        hb.pack_start(e, True, True, 0)
        vbox.pack_start(hb, False, True, 0)
        f = qltk.Frame(_("Tag Editing"), child=vbox)

        close = Button(_("_Close"), icons.WINDOW_CLOSE)
        connect_obj(close, 'clicked', lambda x: x.destroy(), self)
        button_box = Gtk.HButtonBox()
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        button_box.pack_start(close, True, True, 0)

        main_vbox = Gtk.VBox(spacing=12)
        main_vbox.pack_start(f, True, True, 0)
        self.use_header_bar()
        if not self.has_close_button():
            main_vbox.pack_start(button_box, False, True, 0)
        self.add(main_vbox)

        connect_obj(self, 'destroy', PreferencesWindow.__destroy, self)
        self.get_child().show_all()

    def __changed(self, entry, section, name):
        config.set(section, name, entry.get_text())

    def __destroy(self):
        config.write(const.CONFIG)
