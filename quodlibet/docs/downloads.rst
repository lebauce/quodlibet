.. _Downloads:

.. |ubuntu-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/ubuntu.png
   :height: 16
   :width: 16
.. |debian-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/debian.png
   :height: 16
   :width: 16
.. |fedora-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/fedora.png
   :height: 16
   :width: 16
.. |opensuse-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/opensuse.png
   :height: 16
   :width: 16
.. |windows-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/windows.png
   :height: 16
   :width: 16
.. |source-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/source.png
   :height: 16
   :width: 16
.. |hg-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/mercurial.png
   :height: 16
   :width: 16
.. |arch-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/arch.png
   :height: 16
   :width: 16
.. |macosx-logo| image:: http://bitbucket.org/lazka/quodlibet-files/raw/default/icons/macosx.png
   :height: 16
   :width: 16


Downloads
=========

================ ========================================== ================================================
**Linux:**       |ubuntu-logo| :ref:`Ubuntu <ubuntu>`       |debian-logo| :ref:`Debian <debian>`
   \             |fedora-logo| :ref:`Fedora <fedora>`       |opensuse-logo| :ref:`openSUSE <opensuse>`
   \             |arch-logo| :ref:`Arch Linux <arch>`
**Windows:**     |windows-logo| :ref:`Windows <windows>`
**Mac OS X:**    |macosx-logo| :ref:`Mac OS X <macosx>`
**Development:** |hg-logo| :ref:`Source <source>`           |source-logo| :ref:`Release Tarballs <tarballs>`
================ ========================================== ================================================

----

.. _source:

|hg-logo| Source
----------------

Quod Libet uses `Mercurial <http://mercurial.selenic.com/>`_ for source
control and is hosted on `Google Code <https://code.google.com/>`_ as well
as `Bitbucket <https://bitbucket.org/>`__:

 * https://code.google.com/p/quodlibet (primary)
 * https://bitbucket.org/lazka/quodlibet (mirror)

.. _RunFromSource:

**Running from Source** (no installation is needed) **:**

::

    $ hg clone https://code.google.com/p/quodlibet/
    $ ./quodlibet/quodlibet/quodlibet.py

.. note::

    To get all the dependencies needed for running Quod Libet the easiest way
    is to use one of the unstable PPAs / repos listed below. They pull in or
    contain all the needed dependencies for the latest code and are kept up to
    date.


.. _tarballs:

|source-logo| Release Tarballs
------------------------------

========================== ===============================
Release                    Filename
========================== ===============================
Quod Libet 3.3.1           quodlibet-3.3.1.tar.gz_
Quod Libet 3.2.2           quodlibet-3.2.2.tar.gz_
Quod Libet 3.1.2           quodlibet-3.1.2.tar.gz_
Quod Libet Plugins 3.1.2   quodlibet-plugins-3.1.2.tar.gz_
Quod Libet 2.6.3           quodlibet-2.6.3.tar.gz_
Quod Libet Plugins 2.6.3   quodlibet-plugins-2.6.3.tar.gz_
========================== ===============================

.. _quodlibet-3.3.1.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-3.3.1.tar.gz
.. _quodlibet-3.2.2.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-3.2.2.tar.gz
.. _quodlibet-3.1.2.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-3.1.2.tar.gz
.. _quodlibet-plugins-3.1.2.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-plugins-3.1.2.tar.gz
.. _quodlibet-2.6.3.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-2.6.3.tar.gz
.. _quodlibet-plugins-2.6.3.tar.gz: https://bitbucket.org/lazka/quodlibet-files/raw/default/releases/quodlibet-plugins-2.6.3.tar.gz

For old releases see the `full file listing <https://bitbucket.org/lazka/quodlibet-files/src/default/releases>`__.

.. note::

    Since 3.2 all plugins are included in the main tarball


.. _ubuntu:

|ubuntu-logo| Ubuntu
--------------------

Stable PPA (12.04+)::

    $ sudo add-apt-repository ppa:lazka/ppa


Unstable PPA (12.04+)::

    $ sudo add-apt-repository ppa:lazka/dumpingplace


.. note::

    While Ubuntu 12.04 is supported, drag and drop does not work.


.. note::

    To remove the PPAs and revert back to the old version::

        $ sudo add-get install ppa-purge
        $ sudo ppa-purge ppa:lazka/ppa
        $ sudo ppa-purge ppa:lazka/dumpingplace


.. _debian:

|debian-logo| Debian
--------------------

Stable Repo:

* Wheezy (Debian stable)::

    # deb http://lazka.github.io/ql-debian/stable/ quodlibet-stable/
    # deb http://http.debian.net/debian wheezy-backports main

    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 0C693B8F
    sudo apt-get update
    sudo apt-get install quodlibet

Unstable Repo:

* Jessie (Debian testing)::

    # deb http://lazka.github.io/ql-debian/testing/ quodlibet-unstable/

    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 5A62D0CAB6264964
    sudo apt-get update
    sudo apt-get install quodlibet


.. _fedora:

|fedora-logo| Fedora
--------------------

Stable Repo (`OBS <https://build.opensuse.org/project/show/home:lazka0:ql-stable>`__):

  * `Fedora 20 <http://download.opensuse.org/repositories/home:/lazka0:/ql-stable/Fedora_20/home:lazka0:ql-stable.repo>`__

.. note::

    Check out the official repos first, they usually contain the latest stable release: https://apps.fedoraproject.org/packages/quodlibet/overview/

Unstable Repo (`OBS <https://build.opensuse.org/project/show/home:lazka0:ql-unstable>`__):

  * `Fedora 20 <http://download.opensuse.org/repositories/home:/lazka0:/ql-unstable/Fedora_20/home:lazka0:ql-unstable.repo>`__

Unstable Repo (`COPR <http://copr.fedoraproject.org/coprs/lazka/quodlibet-unstable/>`__):

  * `Fedora 21 <http://copr.fedoraproject.org/coprs/lazka/quodlibet-unstable/repo/fedora-21/lazka-quodlibet-unstable-fedora-21.repo>`__
  * `Fedora 20 <http://copr.fedoraproject.org/coprs/lazka/quodlibet-unstable/repo/fedora-20/lazka-quodlibet-unstable-fedora-20.repo>`__
  * `Fedora Rawhide <http://copr.fedoraproject.org/coprs/lazka/quodlibet-unstable/repo/fedora-rawhide/lazka-quodlibet-unstable-fedora-rawhide.repo>`__
  * `RHEL 7 <http://copr.fedoraproject.org/coprs/lazka/quodlibet-unstable/repo/epel-7/lazka-quodlibet-unstable-epel-7.repo>`__


.. _opensuse:

|opensuse-logo| openSUSE
------------------------

Stable Repo:

  * `openSUSE 13.2 <http://download.opensuse.org/repositories/home:/lazka0:/ql-stable/openSUSE_13.2/>`__
  * `openSUSE 13.1 <http://download.opensuse.org/repositories/home:/lazka0:/ql-stable/openSUSE_13.1/>`__
  * `openSUSE Tumbleweed <http://download.opensuse.org/repositories/home:/lazka0:/ql-stable/openSUSE_Tumbleweed>`__

Unstable Repo:

  * `openSUSE 13.2 <http://download.opensuse.org/repositories/home:/lazka0:/ql-unstable/openSUSE_13.2/>`__
  * `openSUSE 13.1 <http://download.opensuse.org/repositories/home:/lazka0:/ql-unstable/openSUSE_13.1/>`__
  * `openSUSE Tumbleweed <http://download.opensuse.org/repositories/home:/lazka0:/ql-unstable/openSUSE_Tumbleweed>`__


.. _arch:

|arch-logo| Arch Linux
----------------------

Stable:

::

    $ pacman -S quodlibet


Unstable:


See `quodlibet-hg <https://aur.archlinux.org/packages/quodlibet-hg>`__ in
the `AUR <https://wiki.archlinux.org/index.php/AUR>`__.


.. _windows:

|windows-logo| Windows
----------------------

=========================== ==============================
Release                     Filename
=========================== ==============================
Quod Libet 3.3.1            quodlibet-3.3.1-installer.exe_
Quod Libet 3.3.1 (portable) quodlibet-3.3.1-portable.exe_
Quod Libet 3.2.2            quodlibet-3.2.2-installer.exe_
Quod Libet 3.2.2 (portable) quodlibet-3.2.2-portable.exe_
Quod Libet 3.1.2            quodlibet-3.1.2-installer.exe_
Quod Libet 3.1.2 (portable) quodlibet-3.1.2-portable.exe_
Quod Libet 2.6.3            quodlibet-2.6.3-installer.exe_
Quod Libet 2.6.3 (portable) quodlibet-2.6.3-portable.exe_
=========================== ==============================

.. _quodlibet-3.3.1-portable.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.3.1-portable.exe
.. _quodlibet-3.3.1-installer.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.3.1-installer.exe
.. _quodlibet-3.2.2-portable.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.2.2-portable.exe
.. _quodlibet-3.2.2-installer.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.2.2-installer.exe
.. _quodlibet-3.1.2-portable.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.1.2-portable.exe
.. _quodlibet-3.1.2-installer.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-3.1.2-installer.exe
.. _quodlibet-2.6.3-portable.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-2.6.3-portable.exe
.. _quodlibet-2.6.3-installer.exe: https://bitbucket.org/lazka/quodlibet/downloads/quodlibet-2.6.3-installer.exe

For old releases see the `full file listing <https://bitbucket.org/lazka/quodlibet/downloads/>`__.


.. _macosx:

|macosx-logo| Mac OS X
----------------------

=========================== ==============================
Release                     Application Bundle
=========================== ==============================
Quod Libet 3.3.1            Quodlibet-3.3.1_0.zip_
Ex False 3.3.1              ExFalso-3.3.1_0.zip_
Quod Libet 3.3.0            Quodlibet-3.3.0_0.zip_
Ex False 3.3.0              ExFalso-3.3.0_0.zip_
=========================== ==============================

.. _Quodlibet-3.3.1_0.zip: https://github.com/elelay/quodlibet-osx-bundle/releases/download/Quodlibet-3.3.1_0/Quodlibet-3.3.1_0.zip
.. _ExFalso-3.3.1_0.zip: https://github.com/elelay/quodlibet-osx-bundle/releases/download/ExFalso-3.3.1_0/ExFalso-3.3.1_0.zip
.. _Quodlibet-3.3.0_0.zip: https://github.com/elelay/quodlibet-osx-bundle/releases/download/Quodlibet-3.3.0_0/Quodlibet-3.3.0_0.zip
.. _ExFalso-3.3.0_0.zip: https://github.com/elelay/quodlibet-osx-bundle/releases/download/Quodlibet-3.3.0_0/ExFalso-3.3.0_0.zip
