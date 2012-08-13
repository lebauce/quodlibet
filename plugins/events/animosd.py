# Copyright (C) 2012 Nick Boultbee, Thomas Vogt
# Copyright (C) 2008 Andreas Bombe
# Copyright (C) 2005  Michael Urman
# Based on osd.py (C) 2005 Ton van den Heuvel, Joe Wreshnig
#                 (C) 2004 Gustavo J. A. M. Carneiro
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
#

import gtk
import gobject
import pango
import cairo
import pangocairo
from math import pi

from quodlibet import config, qltk
from quodlibet.qltk.textedit import PatternEdit
from quodlibet.parse import XMLFromPattern
from quodlibet.plugins.events import EventPlugin
from quodlibet.player import playlist

def Label(text):
    l = gtk.Label(text)
    l.set_alignment(0.0, 0.5)
    return l

class OSDWindow(gtk.Window):
    __gsignals__ = {
            'expose-event': 'override',
            'fade-finished': (gobject.SIGNAL_RUN_LAST, None, (bool,)),
            }

    def __init__(self, conf, song):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_NOTIFICATION)

        # for non-composite operation
        self.background_pixbuf = None
        self.titleinfo_surface = None

        screen = self.get_screen()
        cmap = screen.get_rgba_colormap()
        if cmap is None:
            cmap = screen.get_rgb_colormap()
        self.set_colormap(cmap)

        self.conf = conf
        self.iteration_source = None

        cover = song.find_cover()
        try:
            if cover is not None:
                cover = gtk.gdk.pixbuf_new_from_file(cover.name)
        except gobject.GError, gerror:
            print 'Error while loading cover image:', gerror.message
        except:
            from traceback import print_exc
            print_exc()

        # now calculate size of window
        mgeo = screen.get_monitor_geometry(conf.monitor)
        coverwidth = min(120, mgeo.width // 8)
        textwidth = mgeo.width - 2 * (conf.border + conf.margin)
        if cover is not None:
            textwidth -= coverwidth + conf.border
            coverheight = int(cover.get_height() * (float(coverwidth) /
                cover.get_width()))
        else:
            coverheight = 0
        self.cover_pixbuf = cover

        layout = self.create_pango_layout('')
        layout.set_alignment((pango.ALIGN_LEFT,
                pango.ALIGN_CENTER, pango.ALIGN_RIGHT)[conf.align])
        layout.set_spacing(pango.SCALE * 7)
        layout.set_font_description(pango.FontDescription(conf.font))
        layout.set_markup(XMLFromPattern(conf.string) % song)
        layout.set_width(pango.SCALE * textwidth)
        layoutsize = layout.get_pixel_size()
        if layoutsize[0] < textwidth:
            layout.set_width(pango.SCALE * layoutsize[0])
            layoutsize = layout.get_pixel_size()
        self.title_layout = layout

        winw = layoutsize[0] + 2 * conf.border
        if cover is not None:
            winw += coverwidth + conf.border
        winh = max(coverheight, layoutsize[1]) + 2 * conf.border
        self.set_default_size(winw, winh)

        self.cover_rectangle = gtk.gdk.Rectangle(conf.border,
                (winh - coverheight) // 2, coverwidth, coverheight)

        winx = int((mgeo.width - winw) * conf.pos_x)
        winx = max(conf.margin, min(mgeo.width - conf.margin - winw, winx))
        winy = int((mgeo.height - winh) * conf.pos_y)
        winy = max(conf.margin, min(mgeo.height - conf.margin - winh, winy))
        self.move(winx + mgeo.x, winy + mgeo.y)

    def do_expose_event(self, event):
        cr = self.window.cairo_create()

        if self.is_composited():
            # the simple case
            self.draw_title_info(cr)
            return

        # manual transparency rendering follows
        back_pbuf = self.background_pixbuf
        title_surface = self.titleinfo_surface
        walloc = self.allocation
        wpos = self.get_position()

        if back_pbuf is None:
            root = self.get_screen().get_root_window()
            back_pbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8,
                    walloc.width, walloc.height)
            back_pbuf.get_from_drawable(root, root.get_colormap(),
                    wpos[0], wpos[1], 0, 0, walloc.width, walloc.height)
            self.background_pixbuf = back_pbuf

        if title_surface is None:
            title_surface = gtk.gdk.Pixmap(self.window, walloc.width,
                    walloc.height)
            titlecr = title_surface.cairo_create()
            self.draw_title_info(titlecr)

        cr.set_operator(cairo.OPERATOR_SOURCE)
        if back_pbuf is not None:
            cr.set_source_pixbuf(back_pbuf, 0, 0)
        else:
            cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_pixmap(title_surface, 0, 0)
        cr.paint_with_alpha(self.get_opacity())

    def rounded_rectangle (self, cr, x, y, radius, width, height):
        cr.move_to(x + radius, y)
        cr.line_to(x + width - radius, y)
        cr.arc (x + width - radius, y + radius, radius,
                - 90.0 * pi / 180.0, 0.0 * pi / 180.0)
        cr.line_to(x + width, y + height - radius)
        cr.arc (x + width - radius, y + height - radius, radius,
                0.0 * pi / 180.0, 90.0 * pi / 180.0)
        cr.line_to(x + radius, y + height)
        cr.arc (x + radius, y + height - radius, radius,
                90.0 * pi / 180.0, 180.0 * pi / 180.0)
        cr.line_to(x, y + radius)
        cr.arc (x + radius, y + radius, radius,
                180.0 * pi / 180.0, 270.0 * pi / 180.0)
        cr.close_path()

    def draw_conf_rect(self, cr, x, y, width, height, radius):
        if self.conf.corners != 0:
                self.rounded_rectangle(cr, x, y, radius, width, height)
        else:
                cr.rectangle(x, y, width, height)

    def draw_title_info(self, cr):
        do_shadow = (self.conf.shadow[0] != -1.0)
        do_outline = (self.conf.outline[0] != -1.0)

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.rectangle(0, 0, *self.get_size())
        cr.fill()

        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(*self.conf.fill)
        radius = min(25, self.conf.corners * min(*self.get_size()))
        self.draw_conf_rect(cr, 0, 0, self.get_size()[0], self.get_size()[1], radius)
        cr.fill()

        # draw border
        if (do_outline):
            # Make border darker and more translucent than the fill
            f = self.conf.fill
            rgba = (f[0]/1.25, f[1]/1.25, f[2]/1.25, f[3]/2.0)
            cr.set_source_rgba(*rgba)
            self.draw_conf_rect(cr, 1, 1,
                self.get_size()[0] - 2, self.get_size()[1] - 2, radius)
            cr.set_line_width(2.0)
            cr.stroke()

        textx = self.conf.border

        if self.cover_pixbuf is not None:
            rect = self.cover_rectangle
            textx += rect.width + self.conf.border
            pbuf = self.cover_pixbuf
            transmat = cairo.Matrix()

            if do_shadow:
                cr.set_source_rgba(*self.conf.shadow)
                self.draw_conf_rect(cr, rect.x + 2, rect.y + 2,
                        rect.width, rect.height, 0.6 * self.conf.corners * rect.width)
                cr.fill()

            if do_outline:
                cr.set_source_rgba(*self.conf.outline)
                self.draw_conf_rect(cr, rect.x, rect.y,
                        rect.width, rect.height, 0.6 * self.conf.corners * rect.width)
                cr.stroke()

            cr.set_source_pixbuf(pbuf, 0, 0)
            transmat.scale(pbuf.get_width() / float(rect.width),
                    pbuf.get_height() / float(rect.height))
            transmat.translate(-rect.x, -rect.y)
            cr.get_source().set_matrix(transmat)
            self.draw_conf_rect(cr, rect.x, rect.y,
                 rect.width, rect.height, 0.6 * self.conf.corners * rect.width)
            cr.fill()

        pcc = pangocairo.CairoContext(cr)
        pcc.update_layout(self.title_layout)
        texty = (self.get_size()[1] - self.title_layout.get_pixel_size()[1]) // 2

        if do_shadow:
            cr.set_source_rgba(*self.conf.shadow)
            cr.move_to(textx + 2, texty + 2)
            pcc.show_layout(self.title_layout)
        if do_outline:
            cr.set_source_rgba(*self.conf.outline)
            cr.move_to(textx, texty)
            pcc.layout_path(self.title_layout)
            cr.stroke()
        cr.set_source_rgb(*self.conf.text[:3])
        cr.move_to(textx, texty)
        pcc.show_layout(self.title_layout)

    def fade_in(self):
        self.do_fade_inout(True)

    def fade_out(self):
        self.do_fade_inout(False)

    def do_fade_inout(self, fadein):
        fadein = bool(fadein)

        self.fading_in = fadein
        now = gobject.get_current_time()

        fraction = self.get_opacity()
        if not fadein:
            fraction = 1.0 - fraction
        self.fade_start_time = now - fraction * self.conf.fadetime

        if self.iteration_source is None:
            self.iteration_source = gobject.timeout_add(self.conf.ms,
                    self.fade_iteration_callback)

    def fade_iteration_callback(self):
        delta = gobject.get_current_time() - self.fade_start_time
        fraction = delta / self.conf.fadetime

        if self.fading_in:
            self.set_opacity(fraction)
        else:
            self.set_opacity(1.0 - fraction)

        if not self.is_composited():
            self.queue_draw()

        if fraction >= 1.0:
            self.iteration_source = None
            self.emit('fade-finished', self.fading_in)
            return False
        return True

class AnimOsd(EventPlugin):
    PLUGIN_ID = "Animated On-Screen Display"
    PLUGIN_NAME = _("Animated On-Screen Display")
    PLUGIN_DESC = _("Display song information on your screen when it changes.")
    PLUGIN_VERSION = "1.1"

    def PluginPreferences(self, parent):
        def __coltofloat(x):
            return x / 65535.0

        def __floattocol(x):
            return int(x * 65535)

        def cfg_set_tuple(name, t):
            string = " ".join(map(str,t))
            #print_d("Writing config: %s=%s" % (name, string))
            config.set("plugins", "animosd_%s" % name, string)

        class ConfigLabel(gtk.Label):
            def __init__(self, text, widget):
                super(ConfigLabel, self).__init__(text)
                self.set_use_underline(True)
                self.set_mnemonic_widget(widget)

        def set_text(button):
            color = button.get_color()
            color = map(__coltofloat, (color.red, color.green, color.blue, 0.0))
            self.conf.text = tuple(color)
            cfg_set_tuple("text", self.conf.text)
            self.plugin_single_song(playlist.song)

        def set_fill(button):
            color = button.get_color()
            color = map(__coltofloat, (color.red, color.green, color.blue,
                button.get_alpha()))
            self.conf.fill = tuple(color)
            cfg_set_tuple("fill", self.conf.fill)
            self.plugin_single_song(playlist.song)

        def set_font(button):
            font = button.get_font_name()
            config.set("plugins", "animosd_font", font)
            self.conf.font = font
            self.plugin_single_song(playlist.song)

        def change_delay(button):
            value = int(button.get_value() * 1000)
            config.set("plugins", "animosd_delay", str(value))
            self.conf.delay = value

        def change_monitor(button):
            """Monitor number config change handler"""
            value = int(button.get_value())
            config.set("plugins", "animosd_monitor", str(value))
            self.conf.monitor = value

        def change_position(button):
            value = button.get_active() / 2.0
            config.set("plugins", "animosd_pos_y", str(value))
            self.conf.pos_y = value
            self.plugin_single_song(playlist.song)

        def change_align(button):
            value = button.get_active()
            config.set("plugins", "animosd_align", str(value))
            self.conf.align = value
            self.plugin_single_song(playlist.song)

        def change_shadow(button):
            if button.get_active():
                self.conf.shadow = (0.0, 0.0, 0.0, self.conf.fill[3])
            else:
                self.conf.shadow = (-1.0, 0.0, 0.0, 0.0)
            cfg_set_tuple("shadow", self.conf.shadow)
            self.plugin_single_song(playlist.song)

        def change_outline(button):
            if button.get_active():
                # Vary with fill alpha to create a smoother outline edge
                alpha = (min(1.0, self.conf.fill[3] * 1.25))
                self.conf.outline = (0.1, 0.1, 0.1, alpha)
            else:
                self.conf.outline = (-1.0, 0.0, 0.0)
            cfg_set_tuple("outline", self.conf.outline)
            self.plugin_single_song(playlist.song)

        def change_rounded(button):
            if button.get_active():
                self.conf.corners = 0.14
            else:
                self.conf.corners = 0
            config.set("plugins", "animosd_corners", str(self.conf.corners))
            self.plugin_single_song(playlist.song)

        def edit_string(button):
            w = PatternEdit(button, AnimOsd.conf.string)
            w.text = self.conf.string
            w.apply.connect_object_after('clicked', set_string, w)

        def set_string(window):
            value = window.text
            config.set("plugins", "animosd_string", value)
            self.conf.string = value
            self.plugin_single_song(playlist.song)

        # Main VBox to return
        vb = gtk.VBox(spacing=6)

        # Display
        vb2 = gtk.VBox(spacing=3)
        hb = gtk.HBox(spacing=6)
        # Set monitor to display OSD on if there's more than one
        monitor_cnt = gtk.gdk.screen_get_default().get_n_monitors()
        if monitor_cnt > 1:
            monitor = gtk.SpinButton(
                gtk.Adjustment(value=self.conf.monitor, lower=0,
                upper=monitor_cnt - 1, step_incr=1)
            )
            monitor.set_numeric(True)
            monitor.connect('value-changed', change_monitor)
            l2 = ConfigLabel("_Monitor:", monitor)
            hb.pack_start(l2, expand=False)
            hb.pack_start(monitor, expand=False)
            vb2.pack_start(hb)
        else:
            self.conf.monitor = 0 #should be this by default anyway

        hb = gtk.HBox(spacing=6)
        cb = gtk.combo_box_new_text()
        cb.append_text(_("Top of screen"))
        cb.append_text(_("Middle of screen"))
        cb.append_text(_("Bottom of screen"))
        cb.set_active(int(self.conf.pos_y * 2.0))
        cb.connect('changed', change_position)
        lbl = ConfigLabel(_("_Position:"), cb)

        hb.pack_start(lbl, expand=False)
        hb.pack_start(cb, expand=False)
        vb2.pack_start(hb, expand=False)

        frame = qltk.Frame(label=_("Display"), child=vb2)
        frame.set_border_width(6)
        vb.pack_start(frame, expand=False)

        # Text
        vb2 = gtk.VBox(spacing=6)
        hb = gtk.HBox(spacing=6)
        font = gtk.FontButton()
        font.set_font_name(self.conf.font)
        font.connect('font-set', set_font)
        lbl = ConfigLabel(_("_Font:"), font)
        hb.pack_start(lbl, expand=False)
        hb.pack_start(font)
        vb2.pack_start(hb, expand=False)

        hb = gtk.HBox(spacing=3)
        align = gtk.combo_box_new_text()
        align.append_text(_("Left"))
        align.append_text(_("Center"))
        align.append_text(_("Right"))
        align.set_active(self.conf.align)
        align.connect('changed', change_align)
        lbl = ConfigLabel(_("_Align text:"), align)
        hb.pack_start(lbl, expand=False)
        hb.pack_start(align, expand=False)
        vb2.pack_start(hb, expand=False)

        frame = qltk.Frame(label=_("Text"), child=vb2)
        frame.set_border_width(6)
        vb.pack_start(frame, expand=False)

        # Colors
        t = gtk.Table(2, 2)
        t.set_col_spacings(6)
        t.set_row_spacings(3)
        b = gtk.ColorButton(color=gtk.gdk.Color(*map(__floattocol,
            self.conf.text)))
        l = Label(_("_Text:"))
        l.set_mnemonic_widget(b); l.set_use_underline(True)
        t.attach(l, 0, 1, 0, 1, xoptions=gtk.FILL)
        t.attach(b, 1, 2, 0, 1)
        b.connect('color-set', set_text)
        b = gtk.ColorButton(color=gtk.gdk.Color(*map(__floattocol,
            self.conf.fill[0:3])))
        b.set_use_alpha(True)
        b.set_alpha(__floattocol(self.conf.fill[3]))
        b.connect('color-set', set_fill)
        l = Label(_("_Fill:"))
        l.set_mnemonic_widget(b); l.set_use_underline(True)
        t.attach(l, 0, 1, 1, 2, xoptions=gtk.FILL)
        t.attach(b, 1, 2, 1, 2)

        f = qltk.Frame(label=_("Colors"), child=t)
        f.set_border_width(6)
        vb.pack_start(f, expand=False, fill=False)

        # Effects
        vb2 = gtk.VBox(spacing=3)
        hb = gtk.HBox(spacing=6)
        toggles = [
            ("_Shadows", self.conf.shadow[0], change_shadow),
            ("_Outline", self.conf.outline[0], change_outline),
            ("Rou_nded Corners", self.conf.corners - 1, change_rounded),
            ]

        for (label, current, callback) in toggles:
            checkb = gtk.CheckButton(label)
            checkb.set_active(current != -1)
            checkb.connect("toggled", callback)
            hb.pack_start(checkb)
        vb2.pack_start(hb)

        hb = gtk.HBox(spacing=6)
        timeout = gtk.SpinButton(
            gtk.Adjustment(self.conf.delay / 1000.0, 0, 60, 0.1, 1.0, 0),
            0.1, 1)
        timeout.set_numeric(True)
        timeout.connect('value-changed', change_delay)
        l1 = ConfigLabel("_Delay:", timeout)
        hb.pack_start(l1, expand=False)
        hb.pack_start(timeout, expand=False)
        vb2.pack_start(hb, expand=False)

        frame = qltk.Frame(label=_("Effects"), child=vb2)
        frame.set_border_width(6)
        vb.pack_start(frame, expand=False)


        string = qltk.Button(_("Ed_it Display"), gtk.STOCK_EDIT)
        string.connect('clicked', edit_string)
        vb.pack_start(string, expand=False)
        return vb

    class conf(object):
        pos_x = 0.5 # position of window 0--1 horizontal
        pos_y = 0.0 # position of window 0--1 vertical
        margin = 50 # never any closer to the screen edge than this
        border = 20 # text/cover this far apart, from edge
        fadetime = 0.3 # take this many seconds to fade in or out
        ms = 40 # wait this many milliseconds between steps
        delay = 2500 # wait this many milliseconds before hiding
        monitor = 0 # monitor to display OSD on
        font = "Sans 22"
        text = (0.9, 0.9, 0.9, 0.0) # main font color. Alpha is ignored.
        align = 1 # align text: 0 (left), 1 (center), 2 (right)
        corners = 0 # rounded corner radius, 0 for angled corners
        outline = (-1.0, 0.0, 0.0, 0.2) # color,alpha or (-1.0,0.0,0.0,0.0) - surrounds text and cover
        shadow = (-1.0, 0.0, 0.0, 0.1) # color,alpha or (-1.0,0.0,0.0) - shadows outline for text and cover
        fill = (0.25, 0.25, 0.25, 0.5) # color,alpha or None - fills rectangular area
        bcolor = (0.0, 0.0, 0.0, 0.2) # color,alpha or (-1.0,0.0,0.0,0.5) - borders the whole OSD
        # song information to use - like in main window
        string = r'''<album|\<b\><album>\</b\><discnumber| - Disc <discnumber>><part| - \<b\><part>\</b\>><tracknumber| - <tracknumber>>
>\<span weight='bold' size='large'\><title>\</span\> - <~length><version|
\<small\>\<i\><version>\</i\>\</small\>><~people|
by <~people>>'''

    def __init__(self):
        self.__current_window = None

        def str_to_tuple(s):
            lst = map(float, s.split())
            while len(lst)<4: lst.append(0.0)
            return tuple(lst)

        config_map = [
            ('text', config.get, str_to_tuple),
            ('fill', config.get, str_to_tuple),
            ('shadow', config.get, str_to_tuple),
            ('outline', config.get, str_to_tuple),
            ('bcolor', config.get, str_to_tuple),
            ('corners', config.getfloat, None),
            ('font', config.get, None),
            ('align', config.getint, None),
            ('delay', config.getint, None),
            ('monitor', config.getint, None),
            ('pos_y', config.getfloat, None),
            ('string', config.get, None),
            ]
        for key, cget, getconv in config_map:
            try: value = cget('plugins', 'animosd_' + key)
            except: continue

            try:
                if getconv is not None:
                    value = getconv(value)
            except Exception,err:
                print_d("Error getting config: %s" % err)
            else:
                setattr(self.conf, key, value)

    # for rapid debugging and for the preview
    def plugin_single_song(self, song):
        self.plugin_on_song_started(song)

    def plugin_on_song_started(self, song):
        if self.__current_window is not None:
            if self.__current_window.is_composited():
                self.__current_window.fade_out()
            else:
                self.__current_window.hide()
                self.__current_window.destroy()

        if song is None:
            self.__current_window = None
            return

        window = OSDWindow(self.conf, song)
        window.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        window.connect('button-press-event', self.__buttonpress)
        window.connect('fade-finished', self.__fade_finished)
        self.__current_window = window

        window.set_opacity(0.0)
        window.show()
        window.fade_in()

    def start_fade_out(self, window):
        window.fade_out()
        return False

    def __buttonpress(self, window, event):
        window.hide()
        if self.__current_window is window:
            self.__current_window = None
        window.destroy()

    def __fade_finished(self, window, fade_in):
        if fade_in:
            gobject.timeout_add(self.conf.delay, self.start_fade_out, window)
        else:
            window.hide()
            if self.__current_window is window:
                self.__current_window = None
            # Delay destroy - apparently the hide does not quite register if
            # the destroy is done immediately.  The compiz animation plugin
            # then sometimes triggers and causes undesirable effects while the
            # popup should already be invisible.
            gobject.timeout_add(1000, window.destroy)
