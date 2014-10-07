#!/bin/bash
# Copyright 2013, 2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

trap 'exit 1' SIGINT;

DIR="$( cd "$( dirname "$0" )" && pwd )"
cd "$DIR"

MISC="$DIR"/misc
BIN="$DIR"/_bin
QL_REPO="$DIR"/..
BUILD_BAT="$MISC"/build.bat
BUILD_SDK_BAT="$MISC"/build_sdk.bat
PACKAGE_BAT="$MISC"/package.bat
INST_ICON="$MISC"/quodlibet.ico
NSIS_SCRIPT="$MISC"/win_installer.nsi
BUILD_ENV="$DIR"/_build_env
QL_TEMP="$BUILD_ENV"/ql_temp

function download_and_verify {
    # download all installers and check with sha256sum

    mkdir -p "$BIN"
    if (cd "$BIN" && sha256sum --status --strict -c "$MISC"/filehashes.txt); then
        echo "all installers here, continue.."
    else
        wget -P "$BIN" -c https://bitbucket.org/pypa/setuptools/raw/2.1.1/ez_setup.py
        wget -P "$BIN" -c http://mercurial.selenic.com/release/windows/mercurial-2.8.1-x86.msi
        wget -P "$BIN" -c http://downloads.sourceforge.net/project/nsis/NSIS%202/2.46/nsis-2.46-setup.exe
        wget -P "$BIN" -c http://downloads.sourceforge.net/project/py2exe/py2exe/0.6.9/py2exe-0.6.9.win32-py2.7.exe
        wget -P "$BIN" -c http://bitbucket.org/lazka/quodlibet/downloads/pygi-aio-3.12.2-win32_rev5-setup.exe
        wget -P "$BIN" -c http://downloads.sourceforge.net/project/pyhook/pyhook/1.5.1/pyHook-1.5.1.win32-py2.7.exe
        wget -P "$BIN" -c http://downloads.sourceforge.net/project/pywin32/pywin32/Build%20218/pywin32-218.win32-py2.7.exe
        wget -P "$BIN" -c http://www.python.org/ftp/python/2.7.6/python-2.7.6.msi
        wget -P "$BIN" -c http://downloads.sourceforge.net/sevenzip/7z920.msi
        wget -P "$BIN" -c https://bitbucket.org/lazka/quodlibet/downloads/libmodplug-1.dll
        wget -P "$BIN" -c http://ftp.musicbrainz.org/pub/musicbrainz/python-musicbrainz2/python-musicbrainz2-0.7.4.tar.gz

        pip install --download="$BIN" mutagen==1.22
        pip install --download="$BIN" feedparser==5.1.3

        # check again
        (cd "$BIN" && sha256sum --strict -c "$MISC"/filehashes.txt) || exit
    fi
}

function init_wine {
    # set up wine environ
    export WINEARCH=win32
    export WINEPREFIX="$BUILD_ENV"/wine_env
    export WINEDEBUG=-all

    # try to limit the effect on the host system when installing with wine.
    export HOME="$BUILD_ENV"/home
    export XDG_DATA_HOME="$HOME"/.local/share
    export XDG_CONFIG_HOME="$HOME"/.config
    export XDG_CACHE_HOME="$HOME"/.cache
    export DISPLAY=be_quiet_damnit

     wine wineboot -u
}

function init_build_env {
    # create a fresh build env and link the binaries in
    rm -Rf "$BUILD_ENV"
    mkdir "$BUILD_ENV"
    ln -s "$BIN" "$BUILD_ENV"/bin

    # link the batch file and nsis file in
    ln -s "$BUILD_BAT" "$BUILD_ENV"
    ln -s "$BUILD_SDK_BAT" "$BUILD_ENV"
    ln -s "$PACKAGE_BAT" "$BUILD_ENV"
    ln -s "$NSIS_SCRIPT" "$BUILD_ENV"
    ln -s "$INST_ICON" "$BUILD_ENV"
}

# Argument 1: the hg tag
function clone_repo {

    if [ -z "$1" ]
    then
        echo "missing arg"
        exit 1
    fi

    # clone repo, create translations
    hg clone "$QL_REPO" "$QL_TEMP"
    (cd "$QL_TEMP" && hg up "$1") || exit 1
    QL_VERSION=$(cd "$QL_TEMP"/quodlibet && python -c "import quodlibet.const;print quodlibet.const.VERSION,")

    if [ "$1" = "default" ]
    then
        local HG_REV=$(hg id -n | sed 's/[+]//g')
        local HG_HASH=$(hg id -i | sed 's/[+]//g')
        QL_VERSION="$QL_VERSION-rev$HG_REV-$HG_HASH"
    fi
}

function extract_deps {
    # extract the gi binaries
    PYGI="$BUILD_ENV"/pygi
    echo "extract pygi-aio..."
    7z x -o"$PYGI" -y "$BUILD_ENV"/bin/pygi-aio-3.12.2-win32_rev5-setup.exe > /dev/null
    echo "done"
    echo "extract packages..."
    (cd "$PYGI"/rtvc9/ && find . -name "*.7z" -execdir 7z x -y {} > /dev/null \;)
    (cd "$PYGI"/noarch/ && find . -name "*.7z" -execdir 7z x -y {} > /dev/null \;)
    (cd "$PYGI"/binding/py2.7 && 7z x -y py2.7.7z > /dev/null)
    echo "done"

    # prepare our binary deps
    DEPS="$BUILD_ENV"/deps
    mkdir "$DEPS"

    mv "$PYGI"/noarch/GTKold/ "$PYGI"/noarch/GTKOld/

    for name in rtvc9 noarch; do
        cp -RT "$PYGI"/"$name"/Base/gnome "$DEPS"

        cp -RT "$PYGI"/"$name"/JPEG/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/WebP/gnome "$DEPS"

        cp -RT "$PYGI"/"$name"/GDKOld/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/GDKPixbuf/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/ATK/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Pango/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/GTKOld/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Harfbuzz/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Openraw/gnome "$DEPS"

        cp -RT "$PYGI"/"$name"/Gstreamer/gnome "$DEPS"

        cp -RT "$PYGI"/"$name"/Orc/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/GnuTLS/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Aerial/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Soup/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Jack/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/SQLite/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/GSTPlugins/gnome "$DEPS"

        cp -RT "$PYGI"/"$name"/OpenJPEG/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/Curl/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/IDN/gnome "$DEPS"
        cp -RT "$PYGI"/"$name"/GSTPluginsExtra/gnome "$DEPS"
    done
}

function setup_deps {
    echo "create the icon theme caches"
    wine "$DEPS"/gtk-update-icon-cache.exe "$DEPS"/share/icons/gnome
    wine "$DEPS"/gtk-update-icon-cache.exe "$DEPS"/share/icons/hicolor
    wine "$DEPS"/gtk-update-icon-cache.exe "$DEPS"/share/icons/HighContrast

    echo "compile glib schemas"
    wine "$DEPS"/glib-compile-schemas.exe "$DEPS"/share/glib-2.0/schemas

    echo "set GTK+ settings"
    local GTK_SETTINGS="$DEPS"/etc/gtk-3.0/settings.ini
    echo "[Settings]" > "$GTK_SETTINGS"
    echo "gtk-theme-name = Adwaita" >> "$GTK_SETTINGS"
    echo "gtk-fallback-icon-theme = gnome" >> "$GTK_SETTINGS"
    echo "gtk-xft-antialias = 1" >> "$GTK_SETTINGS"
    echo "gtk-xft-dpi = 98304" >> "$GTK_SETTINGS"
    echo "gtk-xft-hinting = 1" >> "$GTK_SETTINGS"
    echo "gtk-xft-hintstyle = hintfull" >> "$GTK_SETTINGS"
    echo "gtk-xft-rgba = rgb" >> "$GTK_SETTINGS"

    # copy libmodplug
    cp "$BUILD_ENV/bin/libmodplug-1.dll" "$DEPS"
}

function install_python {
    wine msiexec /a "$BUILD_ENV"/bin/python-2.7.6.msi /qb
    PYDIR="$WINEPREFIX"/drive_c/Python27

    # install the python packages
    local SITEPACKAGES="$PYDIR"/Lib/site-packages
    cp -R "$PYGI"/binding/py2.7/cairo "$SITEPACKAGES"
    cp -R "$PYGI"/binding/py2.7/gi "$SITEPACKAGES"
    cp "$PYGI"/binding/py2.7/*.pyd "$SITEPACKAGES"
}

function install_7zip {
    wine msiexec /a "$BUILD_ENV"/bin/7z920.msi /qb
    SZIPDIR="$WINEPREFIX/drive_c/Program Files/7-Zip/"
}

function install_nsis {
    wine "$BUILD_ENV"/bin/nsis-2.46-setup.exe /S
}

function build_quodlibet {
    (cd "$QL_TEMP"/quodlibet && python setup.py build_mo)

    # now run py2exe etc.
    (cd "$BUILD_ENV" && wine cmd /c build.bat)

    QL_DEST="$QL_TEMP"/quodlibet/dist
    QL_BIN="$QL_DEST"/bin

    # python dlls
    cp "$PYDIR"/python27.dll "$QL_BIN"

    # copy deps
    cp "$DEPS"/*.dll "$QL_BIN"
    cp -R "$DEPS"/etc "$QL_DEST"
    cp -R "$DEPS"/lib "$QL_DEST"
    cp -R "$DEPS"/share "$QL_DEST"

    # remove translatins we don't support
    QL_LOCALE="$QL_TEMP"/quodlibet/build/share/locale
    MAIN_LOCALE="$QL_DEST"/share/locale
    python "$MISC"/prune_translations.py "$QL_LOCALE" "$MAIN_LOCALE"

    # copy the translations
    cp -RT "$QL_LOCALE" "$MAIN_LOCALE"
    # remove the gtk30-properties domain -> not visible to the user
    find "$MAIN_LOCALE" -name "gtk30-properties.mo" -exec rm {} \;

    # remove gtk themes except HighContrast/Adwaita/Default
    GTK_THEMES="$QL_DEST"/share/themes
    rm -Rf "$GTK_THEMES"/DeLorean
    rm -Rf "$GTK_THEMES"/Emacs
    rm -Rf "$GTK_THEMES"/Evolve
    rm -Rf "$GTK_THEMES"/Greybird

    # remove ladspa, frei0r
    rm -Rf "$QL_DEST"/lib/frei0r-1
    rm -Rf "$QL_DEST"/lib/ladspa-1

    # remove some large gstreamer plugins..
    GST_LIBS="$QL_DEST"/lib/gstreamer-1.0
    rm -f "$GST_LIBS"/libgstflite.dll # Flite speech synthesizer plugin
    rm -f "$GST_LIBS"/libgstopencv.dll # OpenCV Plugins
    rm -f "$GST_LIBS"/libgstx264.dll # H264 plugins
    rm -f "$GST_LIBS"/libgstcacasink.dll # Colored ASCII Art video sink
    rm -f "$GST_LIBS"/libgstschro.dll # Schroedinger plugin
    rm -f "$GST_LIBS"/libgstjack.dll # Jack sink/source
    rm -f "$GST_LIBS"/libgstpulse.dll # Pulse sink
    rm -f "$GST_LIBS"/libgstvpx.dll # VP8

    # and some other stuff we don't need
    rm -Rf "$QL_DEST"/share/gst-plugins-bad
}

function package_installer {
    # now package everything up
    (cd "$BUILD_ENV" && wine cmd /c package.bat)
    mv "$BUILD_ENV/quodlibet-LATEST.exe" "$DIR/quodlibet-$QL_VERSION-installer.exe"
}

function package_portable_installer {
    local PORTABLE="$BUILD_ENV/quodlibet-$QL_VERSION-portable"
    mkdir "$PORTABLE"

    cp "$MISC"/quodlibet.lnk "$PORTABLE"
    cp "$MISC"/exfalso.lnk "$PORTABLE"
    cp "$MISC"/README-PORTABLE.txt "$PORTABLE"/README.txt
    mkdir "$PORTABLE"/config
    PORTABLE_DATA="$PORTABLE"/data
    mkdir "$PORTABLE_DATA"
    cp -RT "$QL_DEST" "$PORTABLE_DATA"
    cp "$MISC"/conf.py "$PORTABLE_DATA"/bin/quodlibet/

    wine "$SZIPDIR"/7z.exe a "$BUILD_ENV"/portable-temp.7z "$PORTABLE"
    cat "$SZIPDIR"/7z.sfx "$BUILD_ENV"/portable-temp.7z > "$DIR/quodlibet-$QL_VERSION-portable.exe"
    rm "$BUILD_ENV"/portable-temp.7z
}

function setup_sdk {
    SDK="$BUILD_ENV"/quodlibet-win-sdk
    mkdir "$SDK"

    (cd "$BUILD_ENV" && wine cmd /c build_sdk.bat)

    # launchers, README
    ln -s "$MISC"/env.bat "$SDK"
    ln -s "$MISC"/test.bat "$SDK"
    ln -s "$MISC"/wine.sh "$SDK"
    ln -s "$MISC"/test.sh "$SDK"
    ln -s "$MISC"/README-SDK.txt "$SDK"/README.txt

    # bin deps
    ln -s "$DEPS" "$SDK"/deps
    ln -s "$PYDIR" "$SDK"/python

    # ql
    ln -s "$QL_REPO"/quodlibet "$SDK"/quodlibet

    # link to base dir
    ln -s "$SDK" "$DIR"/_sdk
}


function cleanup {
    # no longer needed, save disk space
    rm -Rf "$PYGI"
}
