# -*- coding: utf-8 -*-
# Copyright 2005 Eduardo Gonzalez <wm.eddie@gmail.com>, Niklas Janlert
#           2006 Joe Wreschnig
#           2008 Antonio Riva, Eduardo Gonzalez <wm.eddie@gmail.com>,
#                Anthony Bretaudeau <wxcover@users.sourceforge.net>,
#                Jeremy Cantrell <jmcantrell@gmail.com>
#           2010 Aymeric Mansoux <aymeric@goto10.org>
#           2008-2013 Christoph Reiter
#           2011-2014 Nick Boultbee
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import os
import time
import threading
import gzip

import urllib
import urllib2
from cStringIO import StringIO
from xml.dom import minidom

from gi.repository import Gtk, Pango, GLib, Gdk, GdkPixbuf
from quodlibet.parse._pattern import ArbitraryExtensionFileFromPattern
from quodlibet.plugins import PluginConfigMixin
from quodlibet.util import format_size, print_exc
from quodlibet.util.dprint import print_d

from quodlibet import util, qltk, print_w, app
from quodlibet.qltk.views import AllTreeView
from quodlibet.qltk.image import (set_renderer_from_pbosf, get_scale_factor,
    get_pbosf_for_pixbuf, set_image_from_pbosf)
from quodlibet.plugins.songsmenu import SongsMenuPlugin
from quodlibet.util.path import iscommand
from quodlibet.util import thumbnails


USER_AGENT = "Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.2.13) " \
    "Gecko/20101210 Iceweasel/3.6.13 (like Firefox/3.6.13)"

PLUGIN_CONFIG_SECTION = 'cover'
CONFIG_ENG_PREFIX = 'engine_'


def get_encoding_from_socket(socket):
    content_type = socket.headers.get("Content-Type", "")
    p = map(str.strip, map(str.lower, content_type.split(";")))
    enc = [t.split("=")[-1].strip() for t in p if t.startswith("charset")]
    return (enc and enc[0]) or "utf-8"


def get_url(url, post={}, get={}):
    post_params = urllib.urlencode(post)
    get_params = urllib.urlencode(get)
    if get:
        get_params = '?' + get_params

    # add post, get data and headers
    url = '%s%s' % (url, get_params)
    if post_params:
        request = urllib2.Request(url, post_params)
    else:
        request = urllib2.Request(url)

    # for discogs
    request.add_header('Accept-Encoding', 'gzip')
    request.add_header('User-Agent', USER_AGENT)

    url_sock = urllib2.urlopen(request)
    enc = get_encoding_from_socket(url_sock)

    # unzip the response if needed
    data = url_sock.read()
    if url_sock.headers.get("content-encoding", "") == "gzip":
        data = gzip.GzipFile(fileobj=StringIO(data)).read()
    url_sock.close()

    return data, enc


def get_encoding(url):
    request = urllib2.Request(url)
    request.add_header('Accept-Encoding', 'gzip')
    request.add_header('User-Agent', USER_AGENT)
    url_sock = urllib2.urlopen(request)
    return get_encoding_from_socket(url_sock)


class AmazonParser(object):
    """A class for searching covers from Amazon"""

    def __init__(self):
        self.page_count = 0
        self.covers = []
        self.limit = 0

    def __parse_page(self, page, query):
        """Gets all item tags and calls the item parsing function for each"""

        # Amazon now requires that all requests be signed.
        # I have built a webapp on AppEngine for this purpose. -- wm_eddie
        # url = 'http://webservices.amazon.com/onca/xml'
        url = 'http://qlwebservices.appspot.com/onca/xml'

        parameters = {
            'Service': 'AWSECommerceService',
            'AWSAccessKeyId': '0RKH4ZH1JCFZHMND91G2', # Now Ignored.
            'Operation': 'ItemSearch',
            'ResponseGroup': 'Images,Small',
            'SearchIndex': 'Music',
            'Keywords': query,
            'ItemPage': page,
            # This specifies where the money goes and needed since 1.11.2011
            # (What a good reason to break API..)
            # ...so use the gnome.org one
            'AssociateTag': 'gnomestore-20',
        }
        data, enc = get_url(url, get=parameters)
        dom = minidom.parseString(data)

        pages = dom.getElementsByTagName('TotalPages')
        if pages:
            self.page_count = int(pages[0].firstChild.data)

        items = dom.getElementsByTagName('Item')

        for item in items:
            self.__parse_item(item)
            if len(self.covers) >= self.limit:
                break

    def __parse_item(self, item):
        """Extract all information and add the covers to the list."""

        large = item.getElementsByTagName('LargeImage')
        small = item.getElementsByTagName('SmallImage')
        title = item.getElementsByTagName('Title')

        if large and small and title:
            cover = {}

            artist = item.getElementsByTagName('Artist')
            creator = item.getElementsByTagName('Creator')

            text = ''
            if artist:
                text = artist[0].firstChild.data
            elif creator:
                if len(creator) > 1:
                    text = ', '.join([i.firstChild.data for i in creator])
                else:
                    text = creator[0].firstChild.data

            title_text = title[0].firstChild.data

            if len(text) and len(title_text):
                text += ' - '

            cover['name'] = text + title_text

            url_tag = small[0].getElementsByTagName('URL')[0]
            cover['thumbnail'] = url_tag.firstChild.data

            url_tag = large[0].getElementsByTagName('URL')[0]
            cover['cover'] = url_tag.firstChild.data

            #Since we don't know the size, use the one from the HTML header.
            cover['size'] = get_size_of_url(cover['cover'])

            h_tag = large[0].getElementsByTagName('Height')[0]
            height = h_tag.firstChild.data

            w_tag = large[0].getElementsByTagName('Width')[0]
            width = w_tag.firstChild.data

            cover['resolution'] = '%s x %s px' % (width, height)

            cover['source'] = 'http://www.amazon.com'

            self.covers.append(cover)

    def start(self, query, limit=10):
        """Start the search and returns the covers"""

        self.page_count = 0
        self.covers = []
        self.limit = limit
        self.__parse_page(1, query)

        if len(self.covers) < limit:
            for page in xrange(2, self.page_count + 1):
                self.__parse_page(page, query)
                if len(self.covers) >= limit:
                    break

        return self.covers


class CoverArea(Gtk.VBox, PluginConfigMixin):
    """The image display and saving part."""

    CONFIG_SECTION = PLUGIN_CONFIG_SECTION

    def __init__(self, parent, song):
        super(CoverArea, self).__init__()
        self.song = song

        self.dirname = song("~dirname")
        self.main_win = parent

        self.data_cache = []
        self.current_data = None
        self.current_pixbuf = None

        self.image = Gtk.Image()
        self.button = Gtk.Button(stock=Gtk.STOCK_SAVE)
        self.button.set_sensitive(False)
        self.button.connect('clicked', self.__save)

        close_button = Gtk.Button(stock=Gtk.STOCK_CLOSE)
        close_button.connect('clicked', lambda x: self.main_win.destroy())

        self.window_fit = self.ConfigCheckButton(_('Fit image to _window'),
                                                 'fit', True)
        self.window_fit.connect('toggled', self.__scale_pixbuf)

        self.name_combo = Gtk.ComboBoxText()

        self.cmd = qltk.entry.ValidatingEntry(iscommand)

        # Both labels
        label_open = Gtk.Label(label=_('_Program:'))
        label_open.set_use_underline(True)
        label_open.set_mnemonic_widget(self.cmd)
        label_open.set_justify(Gtk.Justification.LEFT)

        self.open_check = self.ConfigCheckButton(_('_Edit image after saving'),
                                                 'edit', False)
        label_name = Gtk.Label(label=_('File_name:'), use_underline=True)
        label_name.set_use_underline(True)
        label_name.set_mnemonic_widget(self.name_combo)
        label_name.set_justify(Gtk.Justification.LEFT)

        self.cmd.set_text(self.config_get('edit_cmd', 'gimp'))

        # Create the filename combo box
        fn_list = ['cover.jpg', 'folder.jpg', '.folder.jpg']

        # Issue 374 - add dynamic file names
        artist = song("artist")
        alartist = song("albumartist")
        album = song("album")
        labelid = song("labelid")
        if album:
            fn_list.append("<album>.jpg")
            if alartist:
                fn_list.append("<albumartist> - <album>.jpg")
            else:
                fn_list.append("<artist> - <album>.jpg")
        else:
            print_w("No album for \"%s\". Could be difficult finding art..." %
                    song("~filename"))
            title = song("title")
            if title and artist:
                fn_list.append("<artist> - <title>.jpg")
        if labelid:
            fn_list.append("<labelid>.jpg")

        set_fn = self.config_get('fn', fn_list[0])

        for i, fn in enumerate(fn_list):
                self.name_combo.append_text(fn)
                if fn == set_fn:
                    self.name_combo.set_active(i)

        if self.name_combo.get_active() < 0:
            self.name_combo.set_active(0)

        table = Gtk.Table(rows=2, columns=2, homogeneous=False)
        table.set_row_spacing(0, 5)
        table.set_row_spacing(1, 5)
        table.set_col_spacing(0, 5)
        table.set_col_spacing(1, 5)

        table.attach(label_open, 0, 1, 0, 1)
        table.attach(label_name, 0, 1, 1, 2)

        table.attach(self.cmd, 1, 2, 0, 1)
        table.attach(self.name_combo, 1, 2, 1, 2)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.add_with_viewport(self.image)
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,
                                 Gtk.PolicyType.AUTOMATIC)

        bbox = Gtk.HButtonBox()
        bbox.set_spacing(6)
        bbox.set_layout(Gtk.ButtonBoxStyle.END)
        bbox.pack_start(self.button, True, True, 0)
        bbox.pack_start(close_button, True, True, 0)

        bb_align = Gtk.Alignment.new(0, 1, 1, 0)
        bb_align.set_property('right-padding', 6)
        bb_align.add(bbox)

        main_hbox = Gtk.HBox()
        main_hbox.pack_start(table, False, True, 6)
        main_hbox.pack_start(bb_align, True, True, 0)

        top_hbox = Gtk.HBox()
        top_hbox.pack_start(self.open_check, True, True, 0)
        top_hbox.pack_start(self.window_fit, False, True, 0)

        main_vbox = Gtk.VBox()
        main_vbox.pack_start(top_hbox, True, True, 2)
        main_vbox.pack_start(main_hbox, True, True, 0)

        self.pack_start(self.scrolled, True, True, 0)
        self.pack_start(main_vbox, False, True, 5)

        # 5 MB image cache size
        self.max_cache_size = 1024 * 1024 * 5

        # For managing fast selection switches of covers..
        self.stop_loading = False
        self.loading = False
        self.current_job = 0

        self.connect('destroy', self.__save_config)

    def __save(self, *data):
        """Save the cover and spawn the program to edit it if selected"""

        save_format = self.name_combo.get_active_text()
        # Allow use of patterns in creating cover filenames
        pattern = ArbitraryExtensionFileFromPattern(
            save_format.decode("utf-8"))
        filename = pattern.format(self.song)
        print_d("Using '%s' as filename based on %s" % (filename, save_format))
        file_path = os.path.join(self.dirname, filename)

        msg = (_('The file <b>%s</b> already exists.\n\nOverwrite?')
                % util.escape(filename))
        if (os.path.exists(file_path)
                and not qltk.ConfirmAction(None, _('File exists'), msg).run()):
            return

        try:
            f = open(file_path, 'wb')
            f.write(self.current_data)
            f.close()
        except IOError:
            qltk.ErrorMessage(None, _('Saving failed'),
                _('Unable to save "%s".') % file_path).run()
        else:
            if self.open_check.get_active():
                try:
                    util.spawn([self.cmd.get_text(), file_path])
                except:
                    pass

            app.window.emit("artwork-changed", [self.song])

        self.main_win.destroy()

    def __save_config(self, widget):
        self.config_set('edit_cmd', self.cmd.get_text())
        self.config_set('fn', self.name_combo.get_active_text())

    def __update(self, loader, *data):
        """Update the picture while it's loading"""

        if self.stop_loading:
            return
        pixbuf = loader.get_pixbuf()

        def idle_set():
            set_image_from_pbosf(self.image, pixbuf)

        GLib.idle_add(idle_set)

    def __scale_pixbuf(self, *data):
        if not self.current_pixbuf:
            return
        pixbuf = self.current_pixbuf

        if not self.window_fit.get_active():
            pbosf = pixbuf
        else:
            alloc = self.scrolled.get_allocation()
            width = alloc.width
            height = alloc.height
            scale_factor = get_scale_factor(self)
            boundary = (width * scale_factor, height * scale_factor)
            pixbuf = thumbnails.scale(pixbuf, boundary, scale_up=False)
            pbosf = get_pbosf_for_pixbuf(self, pixbuf)

        set_image_from_pbosf(self.image, pbosf)

    def __close(self, loader, *data):
        if self.stop_loading:
            return
        self.current_pixbuf = loader.get_pixbuf()
        GLib.idle_add(self.__scale_pixbuf)

    def set_cover(self, url):
        thr = threading.Thread(target=self.__set_async, args=(url,))
        thr.setDaemon(True)
        thr.start()

    def __set_async(self, url):
        """Manages various things:
        Fast switching of covers (aborting old HTTP requests),
        The image cache, etc."""

        self.current_job += 1
        job = self.current_job

        self.stop_loading = True
        while self.loading:
            time.sleep(0.05)
        self.stop_loading = False

        if job != self.current_job:
            return

        self.loading = True

        GLib.idle_add(self.button.set_sensitive, False)
        self.current_pixbuf = None

        pbloader = GdkPixbuf.PixbufLoader()
        pbloader.connect('closed', self.__close)

        # Look for cached images
        raw_data = None
        for entry in self.data_cache:
            if entry[0] == url:
                raw_data = entry[1]
                break

        if not raw_data:
            pbloader.connect('area-updated', self.__update)

            data_store = StringIO()

            try:
                request = urllib2.Request(url)
                request.add_header('User-Agent', USER_AGENT)
                url_sock = urllib2.urlopen(request)
            except urllib2.HTTPError:
                print_w(_("[albumart] HTTP Error: %s") % url)
            else:
                while not self.stop_loading:
                    tmp = url_sock.read(1024 * 10)
                    if not tmp:
                            break
                    pbloader.write(tmp)
                    data_store.write(tmp)

                url_sock.close()

                if not self.stop_loading:
                    raw_data = data_store.getvalue()

                    self.data_cache.insert(0, (url, raw_data))

                    while 1:
                        cache_sizes = [len(data[1]) for data in
                                       self.data_cache]
                        if sum(cache_sizes) > self.max_cache_size:
                            del self.data_cache[-1]
                        else:
                            break

            data_store.close()
        else:
            # Sleep for fast switching of cached images
            time.sleep(0.05)
            if not self.stop_loading:
                pbloader.write(raw_data)

        try:
            pbloader.close()
        except GLib.GError:
            pass

        self.current_data = raw_data

        if not self.stop_loading:
            GLib.idle_add(self.button.set_sensitive, True)

        self.loading = False


class AlbumArtWindow(qltk.Window, PluginConfigMixin):
    """The main window including the search list"""

    CONFIG_SECTION = PLUGIN_CONFIG_SECTION
    THUMB_SIZE = 50

    def __init__(self, songs):
        super(AlbumArtWindow, self).__init__()

        self.image_cache = []
        self.image_cache_size = 10
        self.search_lock = False

        self.set_title(_('Album Art Downloader'))
        self.set_icon_name(Gtk.STOCK_FIND)
        self.set_default_size(800, 550)

        image = CoverArea(self, songs[0])

        self.liststore = Gtk.ListStore(object, object)
        self.treeview = treeview = AllTreeView(self.liststore)
        self.treeview.set_headers_visible(False)
        self.treeview.set_rules_hint(True)

        targets = [("text/uri-list", 0, 0)]
        targets = [Gtk.TargetEntry.new(*t) for t in targets]

        treeview.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.COPY)

        treeselection = self.treeview.get_selection()
        treeselection.set_mode(Gtk.SelectionMode.SINGLE)
        treeselection.connect('changed', self.__select_callback, image)

        self.treeview.connect("drag-data-get",
            self.__drag_data_get, treeselection)

        rend_pix = Gtk.CellRendererPixbuf()
        img_col = Gtk.TreeViewColumn('Thumb')
        img_col.pack_start(rend_pix, False)

        def cell_data_pb(column, cell, model, iter_, *args):
            pbosf = model[iter_][0]
            set_renderer_from_pbosf(cell, pbosf)

        img_col.set_cell_data_func(rend_pix, cell_data_pb, None)
        treeview.append_column(img_col)

        rend_pix.set_property('xpad', 2)
        rend_pix.set_property('ypad', 2)
        border_width = get_scale_factor(self) * 2
        rend_pix.set_property('width', self.THUMB_SIZE + 4 + border_width)
        rend_pix.set_property('height', self.THUMB_SIZE + 4 + border_width)

        def escape_data(data):
            for rep in ('\n', '\t', '\r', '\v'):
                data = data.replace(rep, ' ')
            return util.escape(' '.join(data.split()))

        def cell_data(column, cell, model, iter, data):
            cover = model[iter][1]

            esc = escape_data

            txt = '<b><i>%s</i></b>' % esc(cover['name'])
            txt += _('\n<small>from <i>%s</i></small>') % esc(cover['source'])
            if 'resolution' in cover:
                txt += _('\nResolution: <i>%s</i>') % esc(cover['resolution'])
            if 'size' in cover:
                txt += _('\nSize: <i>%s</i>') % esc(cover['size'])

            cell.markup = txt
            cell.set_property('markup', cell.markup)

        rend = Gtk.CellRendererText()
        rend.set_property('ellipsize', Pango.EllipsizeMode.END)
        info_col = Gtk.TreeViewColumn('Info', rend)
        info_col.set_cell_data_func(rend, cell_data)

        treeview.append_column(info_col)

        sw_list = Gtk.ScrolledWindow()
        sw_list.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw_list.set_shadow_type(Gtk.ShadowType.IN)
        sw_list.add(treeview)

        self.search_field = Gtk.Entry()
        self.search_button = Gtk.Button(stock=Gtk.STOCK_FIND)
        self.search_button.connect('clicked', self.start_search)
        self.search_field.connect('activate', self.start_search)

        widget_space = 5

        search_hbox = Gtk.HBox(False, widget_space)
        search_hbox.pack_start(self.search_field, True, True, 0)
        search_hbox.pack_start(self.search_button, False, True, 0)

        self.progress = Gtk.ProgressBar()

        left_vbox = Gtk.VBox(False, widget_space)
        left_vbox.pack_start(search_hbox, False, True, 0)
        left_vbox.pack_start(sw_list, True, True, 0)

        hpaned = Gtk.HPaned()
        hpaned.set_border_width(widget_space)
        hpaned.pack1(left_vbox)
        hpaned.pack2(image)
        hpaned.set_position(275)

        self.add(hpaned)

        self.show_all()

        left_vbox.pack_start(self.progress, False, True, 0)

        if songs[0]('albumartist'):
            text = songs[0]('albumartist')
        else:
            text = songs[0]('artist')

        text += ' - ' + songs[0]('album')

        self.set_text(text)
        self.start_search()

    def __drag_data_get(self, view, ctx, sel, tid, etime, treeselection):
        model, iter = treeselection.get_selected()
        if not iter:
            return
        cover = model.get_value(iter, 1)
        sel.set_uris([cover['cover']])

    def start_search(self, *data):
        """Start the search using the text from the text entry"""

        text = self.search_field.get_text()
        if not text or self.search_lock:
            return

        self.search_lock = True
        self.search_button.set_sensitive(False)

        self.progress.set_fraction(0)
        self.progress.set_text(_('Searching...'))
        self.progress.show()

        self.liststore.clear()

        self.search = search = CoverSearch(self.__search_callback)

        for eng in engines:
            if self.config_get(CONFIG_ENG_PREFIX + eng['config_id'], True):
                search.add_engine(eng['class'], eng['replace'])

        search.start(text)

        # Focus the list
        self.treeview.grab_focus()

        self.connect("destroy", self.__destroy)

    def __destroy(self, *args):
        self.search.stop()

    def set_text(self, text):
        """set the text and move the cursor to the end"""

        self.search_field.set_text(text)
        self.search_field.emit('move-cursor', Gtk.MovementStep.BUFFER_ENDS,
            0, False)

    def __select_callback(self, selection, image):
        model, iter = selection.get_selected()
        if not iter:
            return
        cover = model.get_value(iter, 1)
        image.set_cover(cover['cover'])

    def __add_cover_to_list(self, cover):
        try:
            pbloader = GdkPixbuf.PixbufLoader()
            pbloader.write(get_url(cover['thumbnail'])[0])
            pbloader.close()

            scale_factor = get_scale_factor(self)
            size = self.THUMB_SIZE * scale_factor - scale_factor * 2
            pixbuf = pbloader.get_pixbuf().scale_simple(size, size,
                GdkPixbuf.InterpType.BILINEAR)
            pixbuf = thumbnails.add_border(
                pixbuf, 80, round=True, width=scale_factor)
            thumb = get_pbosf_for_pixbuf(self, pixbuf)
        except (GLib.GError, IOError):
            pass
        else:
            def append(data):
                self.liststore.append(data)
            GLib.idle_add(append, [thumb, cover])

    def __search_callback(self, covers, progress):
        for cover in covers:
            self.__add_cover_to_list(cover)

        if self.progress.get_fraction() < progress:
            self.progress.set_fraction(progress)

        if progress >= 1:
            self.progress.set_text(_('Done'))
            GLib.timeout_add(700, self.progress.hide)
            self.search_button.set_sensitive(True)
            self.search_lock = False


class CoverSearch(object):
    """Class for glueing the search engines together. No UI stuff."""

    def __init__(self, callback):
        self.engine_list = []
        self._stop = False

        def wrap(*args, **kwargs):
            if not self._stop:
                return callback(*args, **kwargs)

        self.callback = wrap
        self.finished = 0
        self.overall_limit = 7

    def add_engine(self, engine, query_replace):
        """Adds a new search engine, query_replace is the string with which
        all special characters get replaced"""

        self.engine_list.append((engine, query_replace))

    def stop(self):
        """After stop the progress callback will no longer be called"""

        self._stop = True

    def start(self, query):
        """Start search. The callback function will be called after each of
        the search engines has finished."""

        for engine, replace in self.engine_list:
            thr = threading.Thread(target=self.__search_thread,
                                   args=(engine, query, replace))
            thr.setDaemon(True)
            thr.start()

        #tell the other side that we are finished if there is nothing to do.
        if not len(self.engine_list):
            GLib.idle_add(self.callback, [], 1)

    def __search_thread(self, engine, query, replace):
        """Creates searching threads which call the callback function after
        they are finished"""

        clean_query = self.__cleanup_query(query, replace)
        result = []
        try:
            result = engine().start(clean_query, self.overall_limit)
        except Exception:
            print_w("[AlbumArt] %s: %r" % (engine.__name__, query))
            print_exc()

        self.finished += 1
        #progress is between 0..1
        progress = float(self.finished) / len(self.engine_list)
        GLib.idle_add(self.callback, result, progress)

    def __cleanup_query(self, query, replace):
        """split up at '-', remove some chars, only keep the longest words..
        more false positives but much better results"""

        query = query.lower()
        if query.startswith("the "):
            query = query[4:]

        split = query.split('-')
        replace_str = ('+', '&', ',', '.', '!', '´',
                       '\'', ':', ' and ', '(', ')')
        new_query = ''
        for part in split:
            for stri in replace_str:
                part = part.replace(stri, replace)

            p_split = part.split()
            p_split.sort(lambda x, y: len(y) - len(x))
            p_split = p_split[:max(len(p_split) / 4, max(4 - len(p_split), 2))]

            new_query += ' '.join(p_split) + ' '

        return new_query.rstrip()


#------------------------------------------------------------------------------
def get_size_of_url(url):
    request = urllib2.Request(url)
    request.add_header('Accept-Encoding', 'gzip')
    request.add_header('User-Agent', USER_AGENT)
    url_sock = urllib2.urlopen(request)
    size = url_sock.headers.get('content-length')
    url_sock.close()
    return format_size(int(size)) if size else ''

#------------------------------------------------------------------------------
engines = [
    {
        'class': AmazonParser,
        'url': 'http://www.amazon.com/',
        'replace': ' ',
        'config_id': 'amazon',
    },
]
#------------------------------------------------------------------------------


class DownloadAlbumArt(SongsMenuPlugin, PluginConfigMixin):
    """Download and save album (cover) art from a variety of sources"""

    PLUGIN_ID = 'Download Album Art'
    PLUGIN_NAME = _('Download Album Art')
    PLUGIN_DESC = _('Download album covers from various websites')
    PLUGIN_ICON = Gtk.STOCK_FIND
    PLUGIN_VERSION = '0.5.2'
    CONFIG_SECTION = PLUGIN_CONFIG_SECTION

    @classmethod
    def PluginPreferences(cls, window):
        table = Gtk.Table(len(engines), 2)
        table.set_col_spacings(6)
        table.set_row_spacings(6)
        frame = qltk.Frame(_("Sources"), child=table)

        for i, eng in enumerate(sorted(engines, key=lambda x: x["url"])):
            check = cls.ConfigCheckButton(
                eng['config_id'].title(),
                CONFIG_ENG_PREFIX + eng['config_id'],
                True)
            table.attach(check, 0, 1, i, i + 1)

            button = Gtk.Button(eng['url'])
            button.connect('clicked', lambda s: util.website(s.get_label()))
            table.attach(button, 1, 2, i, i + 1,
                         xoptions=Gtk.AttachOptions.FILL |
                         Gtk.AttachOptions.SHRINK)
        return frame

    def plugin_album(self, songs):
        return AlbumArtWindow(songs)
