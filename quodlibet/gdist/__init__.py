# -*- coding: utf-8 -*-
# Copyright 2007 Joe Wreschnig
#
# This software and accompanying documentation, if any, may be freely
# used, distributed, and/or modified, in any form and for any purpose,
# as long as this notice is preserved. There is no warranty, either
# express or implied, for this software.

"""distutils extensions for GTK+/GObject/Unix

This module contains a Distribution subclass (GDistribution) which
implements build and install commands for operations related to
Python GTK+ and GObject support. This includes installation
of man pages and gettext/intltool support.
"""

import os

try:
    from py2exe import Distribution
except ImportError:
    from distutils.core import Distribution

from distutils.command.build import build as distutils_build
from distutils.command.install import install as distutils_install

from gdist.shortcuts import build_shortcuts, install_shortcuts
from gdist.man import install_man
from gdist.po import build_mo, install_mo, po_stats, update_po
from gdist.icons import install_icons
from gdist.search_provider import install_search_provider
from gdist.dbus_services import build_dbus_services, install_dbus_services
from gdist.appdata import build_appdata, install_appdata


class build(distutils_build):
    """Override the default build with new subcommands."""

    user_options = distutils_build.user_options + [
        ("skip-po-update", None, "Don't update pot/po files"),
    ]

    sub_commands = distutils_build.sub_commands + [
        ("build_mo",
         lambda self: self.distribution.has_po()),
        ("build_shortcuts",
         lambda self: self.distribution.has_shortcuts()),
        ("build_dbus_services",
         lambda self: self.distribution.has_dbus_services()),
        ("build_appdata",
         lambda self: self.distribution.has_appdata()),
    ]

    def initialize_options(self):
        distutils_build.initialize_options(self)
        self.skip_po_update = False

    def finalize_options(self):
        distutils_build.finalize_options(self)
        self.skip_po_update = bool(self.skip_po_update)


class install(distutils_install):
    """Override the default install with new subcommands."""

    user_options = distutils_install.user_options + [
        ("mandir=", None, "destination directory for man pages. "
                          "Defaults to $PREFIX/share/man"),
    ]

    sub_commands = distutils_install.sub_commands + [
        ("install_shortcuts", lambda self: self.distribution.has_shortcuts()),
        ("install_man", lambda self: self.distribution.has_man_pages()),
        ("install_mo", lambda self: self.distribution.has_po()),
        ("install_icons", lambda self: self.distribution.need_icon_install()),
        ("install_search_provider",
         lambda self: self.distribution.need_search_provider()),
        ("install_dbus_services",
         lambda self: self.distribution.has_dbus_services()),
        ("install_appdata",
         lambda self: self.distribution.has_appdata()),
    ]

    def initialize_options(self):
        distutils_install.initialize_options(self)
        self.mandir = None


class GDistribution(Distribution):
    """A Distribution with support for GTK+-related options

    The GDistribution class adds a number of commads and parameters
    related to GTK+ and GObject Python programs and libraries.

    Parameters (to distutils.core.setup):
      po_directory -- directory where .po files are contained
      po_package -- package name for translation files
      shortcuts -- list of .desktop files to build/install
      dbus_services -- list of .service files to build/install
      man_pages -- list of man pages to install
      appdata -- list of appdata files to install

    Using the translation features requires intltool.

    Example:
      from distutils.core import setup
      from gdist import GDistribution

      setup(distclass=GDistribution, ...)
      """

    shortcuts = []
    appdata = []
    dbus_services = []
    po_directory = None
    man_pages = []
    po_package = None
    search_provider = None

    def __init__(self, *args, **kwargs):
        Distribution.__init__(self, *args, **kwargs)
        self.cmdclass.setdefault("build_mo", build_mo)
        self.cmdclass.setdefault("build_shortcuts", build_shortcuts)
        self.cmdclass.setdefault("build_dbus_services", build_dbus_services)
        self.cmdclass.setdefault("build_appdata", build_appdata)
        self.cmdclass.setdefault("install_icons", install_icons)
        self.cmdclass.setdefault("install_shortcuts", install_shortcuts)
        self.cmdclass.setdefault("install_dbus_services",
                                 install_dbus_services)
        self.cmdclass.setdefault("install_man", install_man)
        self.cmdclass.setdefault("install_mo", install_mo)
        self.cmdclass.setdefault("install_search_provider",
                                 install_search_provider)
        self.cmdclass.setdefault("install_appdata", install_appdata)
        self.cmdclass.setdefault("build", build)
        self.cmdclass.setdefault("install", install)
        self.cmdclass.setdefault("po_stats", po_stats)
        self.cmdclass.setdefault("update_po", update_po)

    def has_po(self):
        return os.name != 'nt' and bool(self.po_directory)

    def has_shortcuts(self):
        return os.name != 'nt' and bool(self.shortcuts)

    def has_appdata(self):
        return os.name != 'nt' and bool(self.appdata)

    def has_man_pages(self):
        return os.name != 'nt' and bool(self.man_pages)

    def has_dbus_services(self):
        return os.name != 'nt' and bool(self.dbus_services)

    def need_icon_install(self):
        return os.name != 'nt'

    def need_search_provider(self):
        return os.name != 'nt'

__all__ = ["GDistribution"]
