#!/bin/bash
# Copyright 2013, 2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

DIR="$( cd "$( dirname "$0" )" && pwd )"

source "$DIR"/_base.sh

# Argument 1: hg tag, defaults to "default"
function build_all {
    local HG_TAG=${1:-"default"}

    echo "Building for hg tag '$HG_TAG'"

    download_and_verify;

    init_wine;
    init_build_env;
    clone_repo "$HG_TAG";
    extract_deps;

    setup_deps;
    install_python;
    install_pydeps;
    install_7zip;
    install_nsis;

    cleanup;
    build_quodlibet;
}

build_all "$1";

package_installer;
package_portable_installer;
