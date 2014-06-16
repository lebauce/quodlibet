#!/usr/bin/env python2
# Copyright 2004-2005 Joe Wreschnig, Niklas Janlert
#           2012 Christoph Reiter
# <quod-libet-development@googlegroups.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import os
import sys

if sys.version_info[0] != 2:
    try:
        os.execvp("python2", ["python"] + sys.argv)
    except OSError:
        pass

import quodlibet
from quodlibet import app
from quodlibet import util
from quodlibet import const
from quodlibet import config


def main():
    quodlibet._init_signal(app.quit)

    opts = util.OptionParser(
        "Ex Falso", const.VERSION,
        _("an audio tag editor"), "[%s]" % _("directory"))

    sys.argv.append(os.path.abspath("."))
    opts, args = opts.parse()
    args[0] = os.path.realpath(args[0])

    config.init(const.CONFIG)

    app.library = quodlibet.init(icon="exfalso",
                                 name="Ex Falso",
                                 title=const.PROCESS_TITLE_EF)
    app.player = quodlibet.init_backend("nullbe", app.librarian)
    pm = quodlibet.init_plugins()
    pm.rescan()

    from quodlibet.qltk.exfalsowindow import ExFalsoWindow
    app.window = ExFalsoWindow(app.library, args[0])
    app.window.init_plugins()

    from quodlibet.qltk import session
    session.init("exfalso")

    quodlibet.enable_periodic_save(save_library=False)
    quodlibet.main(app.window)

    config.save(const.CONFIG)

    print_d("Finished shutdown.")


if __name__ == "__main__":
    main()
