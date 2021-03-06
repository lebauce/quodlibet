#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import sys
import os
import shutil
import subprocess
import tarfile

# disable translations
os.environ["QUODLIBET_NO_TRANS"] = ""

from distutils.core import setup, Command
from distutils.dep_util import newer
from distutils import dir_util
from distutils.command.build_scripts import build_scripts as du_build_scripts

from gdist import GDistribution
from gdist.clean import clean
from distutils.command.sdist import sdist


# TODO: link this better to the app definitions
MIN_PYTHON_VER = (2, 6)
MIN_PYTHON_VER_STR = ".".join(map(str, MIN_PYTHON_VER))


class build_sphinx(Command):
    description = "build sphinx documentation"
    user_options = [
        ("build-dir=", "d", "build directory"),
    ]

    def initialize_options(self):
        self.build_dir = None

    def finalize_options(self):
        self.build_dir = self.build_dir or "build"

    def run(self):
        DOCS_ROOT = "docs"
        GUIDE_ROOT = os.path.join(DOCS_ROOT, "guide")
        TARGET = os.path.join(self.build_dir, "sphinx")

        self.spawn(["sphinx-build", "-b", "html", "-c", DOCS_ROOT,
                    "-n", GUIDE_ROOT, TARGET])


class test_cmd(Command):
    description = "run automated tests"
    user_options = [
        ("to-run=", None, "list of tests to run (default all)"),
        ("suite=", None, "test suite (folder) to run (default 'tests')"),
        ("strict", None, "make glib warnings / errors fatal"),
        ("all", None, "run all suites"),
        ("exitfirst", "x", "stop after first failing test"),
    ]
    use_colors = sys.stderr.isatty() and os.name != "nt"

    def initialize_options(self):
        self.to_run = []
        self.suite = None
        self.strict = False
        self.all = False
        self.exitfirst = False

    def finalize_options(self):
        if self.to_run:
            self.to_run = self.to_run.split(",")
        self.strict = bool(self.strict)
        self.all = bool(self.all)
        self.suite = self.suite and str(self.suite)
        self.exitfirst = bool(self.exitfirst)

    @classmethod
    def _red(cls, text):
        from quodlibet.util.dprint import Colorise
        return Colorise.red(text) if cls.use_colors else text

    def run(self):
        mods = sys.modules.keys()
        if "gi" in mods:
            raise SystemExit("E: setup.py shouldn't depend on gi")

        import tests

        main = False
        if not self.suite or self.all:
            main = True

        subdirs = []
        if self.all:
            test_path = tests.__path__[0]
            for entry in os.listdir(test_path):
                if os.path.isdir(os.path.join(test_path, entry)):
                    subdirs.append(entry)
        elif self.suite:
            subdirs.append(self.suite)

        failures, errors = tests.unit(self.to_run, main=main, subdirs=subdirs,
                                      strict=self.strict,
                                      stop_first=self.exitfirst)
        if failures or errors:
            raise SystemExit(self._red("%d test failure(s) and "
                                       "%d test error(s), as detailed above."
                             % (failures, errors)))


class quality_cmd(Command):
    description = "Run pep8/pyflakes tests"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        cmd = self.reinitialize_command("test")
        cmd.suite = "quality"
        cmd.ensure_finalized()
        cmd.run()


class distcheck(sdist):
    description = "run tests on a fresh sdist"

    def _check_manifest(self):
        assert self.get_archive_files()

        # make sure MANIFEST.in includes all tracked files
        if subprocess.call(["hg", "status"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE) == 0:
            # contains the packaged files after run() is finished
            included_files = self.filelist.files
            assert included_files

            process = subprocess.Popen(["hg", "locate"],
                                       stdout=subprocess.PIPE)
            out, err = process.communicate()
            assert process.returncode == 0

            tracked_files = []
            for path in out.splitlines():
                if not path.startswith("quodlibet" + os.sep):
                    continue
                path = path.split(os.sep, 1)[-1]
                tracked_files.append(path)

            diff = set(tracked_files) ^ set(included_files)
            if diff:
                print("#" * 80)
                print("WARNING: MANFIFEST.in doesn't include all "
                      "tracked files or includes non-tracked files")
                for path in sorted(diff):
                    print(path)
                raise AssertionError

    def _check_dist(self):
        assert self.get_archive_files()

        distcheck_dir = os.path.join(self.dist_dir, "distcheck")
        if os.path.exists(distcheck_dir):
            dir_util.remove_tree(distcheck_dir)
        self.mkpath(distcheck_dir)

        archive = self.get_archive_files()[0]
        tfile = tarfile.open(archive, "r:gz")
        tfile.extractall(distcheck_dir)
        tfile.close()

        name = self.distribution.get_fullname()
        extract_dir = os.path.join(distcheck_dir, name)

        old_pwd = os.getcwd()
        os.chdir(extract_dir)
        self.spawn([sys.executable, "setup.py", "test"])
        self.spawn([sys.executable, "setup.py", "build"])
        self.spawn([sys.executable, "setup.py", "build_sphinx"])
        self.spawn([sys.executable, "setup.py", "install",
                    "--prefix", "../prefix", "--record", "../log.txt"])
        os.chdir(old_pwd)

    def run(self):
        sdist.run(self)
        self._check_manifest()
        self._check_dist()


class build_scripts(du_build_scripts):
    description = "copy scripts to build directory"

    def run(self):
        self.mkpath(self.build_dir)
        for script in self.scripts:
            newpath = os.path.join(self.build_dir, os.path.basename(script))
            if newpath.lower().endswith(".py"):
                newpath = newpath[:-3]
            if newer(script, newpath) or self.force:
                self.copy_file(script, newpath)


class coverage_cmd(Command):
    description = "generate test coverage data"
    user_options = [
        ("to-run=", None, "list of tests to run (default all)"),
    ]

    def initialize_options(self):
        self.to_run = []

    def finalize_options(self):
        pass

    def run(self):
        # Wipe existing modules, to make sure coverage data is properly
        # generated for them.
        for key in sys.modules.keys():
            if key.startswith('quodlibet'):
                del(sys.modules[key])

        try:
            from coverage import coverage
        except ImportError:
            print("Missing 'coverage' module. See "
                  "https://pypi.python.org/pypi/coverage or try "
                  "`apt-get install python-coverage`")
            return

        cov = coverage()
        cov.start()

        cmd = self.reinitialize_command("test")
        cmd.to_run = self.to_run[:]
        cmd.ensure_finalized()
        cmd.run()

        dest = os.path.join(os.getcwd(), "coverage")

        cov.stop()
        cov.html_report(
            directory=dest,
            ignore_errors=True,
            include=["quodlibet*", "operon*"])

        print("Coverage summary: file://%s/index.html" % dest)


def recursive_include(base, sub, ext):
    paths = []
    for path, dirs, files in os.walk(os.path.join(base, sub)):
        for f in files:
            if f.split('.')[-1] in ext:
                p = os.path.relpath(os.path.join(path, f), base)
                paths.append(p)
    return paths


def recursive_include_py2exe(dir_, pre, ext):
    all_ = []
    dir_ = os.path.join(dir_, pre)
    for path, dirs, files in os.walk(dir_):
        all_path = []
        for file_ in files:
            if file_.split('.')[-1] in ext:
                all_path.append(os.path.join(path, file_))
        if all_path:
            all_.append((path, all_path))
    return all_


if __name__ == "__main__":
    # distutils depends on setup.py beeing executed from the same dir.
    # Most of our custom commands work either way, but this makes
    # it work in all cases.
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    import quodlibet
    from quodlibet import const

    # find all packages
    package_path = quodlibet.__path__[0]
    packages = []
    for root, dirnames, filenames in os.walk(package_path):
        if "__init__.py" in filenames:
            relpath = os.path.relpath(root, os.path.dirname(package_path))
            package_name = relpath.replace(os.sep, ".")
            packages.append(package_name)

    cmd_classes = {
        'clean': clean,
        "distcheck": distcheck,
        "test": test_cmd,
        "quality": quality_cmd,
        "coverage": coverage_cmd,
        "build_scripts": build_scripts,
        "build_sphinx": build_sphinx,
    }

    package_path = quodlibet.__path__[0]
    package_data_paths = recursive_include(
        package_path, "images", ("svg", "png", "theme"))

    setup_kwargs = {
        'distclass': GDistribution,
        'cmdclass': cmd_classes,
        'name': "quodlibet",
        'version': const.VERSION,
        'url': "http://code.google.com/p/quodlibet/",
        'description': "a music library, tagger, and player",
        'author': "Joe Wreschnig, Michael Urman, & others",
        'author_email': "quod-libet-development@googlegroups.com",
        'maintainer': "Steven Robertson and Christoph Reiter",
        'license': "GNU GPL v2",
        'packages': packages,
        'package_data': {"quodlibet": package_data_paths},
        'scripts': ["quodlibet.py", "exfalso.py", "operon.py"],
        'po_directory': "po",
        'po_package': "quodlibet",
        'shortcuts': ["data/quodlibet.desktop", "data/exfalso.desktop"],
        'dbus_services': [
            "data/net.sacredchao.QuodLibet.service",
            # http://code.google.com/p/quodlibet/issues/detail?id=1268
            #"data/org.mpris.MediaPlayer2.quodlibet.service",
            #"data/org.mpris.quodlibet.service",
        ],
        'appdata': [
            "data/quodlibet.appdata.xml",
            "data/exfalso.appdata.xml",
        ],
        'man_pages': [
            "data/quodlibet.1",
            "data/exfalso.1",
            "data/operon.1",
        ],
        "search_provider": "data/quodlibet-search-provider.ini",
        }

    if os.name == 'nt':

        # taken from http://www.py2exe.org/index.cgi/win32com.shell
        # ModuleFinder can't handle runtime changes to __path__,
        # but win32com uses them
        try:
            # py2exe 0.6.4 introduced a replacement modulefinder.
            # This means we have to add package paths there, not to the
            # built-in one.  If this new modulefinder gets integrated into
            # Python, then we might be able to revert this some day.
            # if this doesn't work, try import modulefinder
            try:
                import py2exe.mf as modulefinder
            except ImportError:
                import modulefinder

            import win32com
            for p in win32com.__path__[1:]:
                modulefinder.AddPackagePath("win32com", p)
            for extra in ["win32com.shell", "win32com.client"]:
                __import__(extra)
                m = sys.modules[extra]
                for p in m.__path__[1:]:
                    modulefinder.AddPackagePath(extra, p)
        except ImportError:
            # no build path setup, no worries.
            pass

        data_files = [('', ['COPYING'])] + recursive_include_py2exe(
            "quodlibet", "images", ("svg", "png", "theme"))

        # py2exe trips over -1 when trying to write version info in the exe
        if setup_kwargs["version"].endswith(".-1"):
            setup_kwargs["version"] = setup_kwargs["version"][:-3]

        CMD_SUFFIX = "-cmd"
        GUI_TOOLS = ["quodlibet", "exfalso"]

        for gui_name in GUI_TOOLS:
            setup_kwargs.setdefault("windows", []).append({
                "script": "%s.py" % gui_name,
                "icon_resources": [(1,
                   os.path.join('..', 'win_installer', 'misc',
                                '%s.ico' % gui_name))],
            })

            # add a cmd version that supports stdout but opens a console
            setup_kwargs.setdefault("console", []).append({
                "script": "%s%s.py" % (gui_name, CMD_SUFFIX),
                "icon_resources": [(1,
                   os.path.join('..', 'win_installer', 'misc',
                                '%s.ico' % gui_name))],
            })
            setup_kwargs["scripts"].append("%s%s.py" % (gui_name, CMD_SUFFIX))

        for cli_name in ["operon"]:
            setup_kwargs.setdefault("console", []).append({
                "script": "%s.py" % cli_name,
            })

        setup_kwargs.update({
            'data_files': data_files,
            'options': {
                'py2exe': {
                    'packages': ('encodings, feedparser, quodlibet, '
                                 'HTMLParser, cairo, musicbrainz2, shelve, '
                                 'json, gi'),
                    'skip_archive': True,
                    'dist_dir': os.path.join('dist', 'bin'),
                }
            }
        })

        for name in GUI_TOOLS:
            shutil.copy("%s.py" % name, "%s%s.py" % (name, CMD_SUFFIX))
        try:
            setup(**setup_kwargs)
        finally:
            for name in GUI_TOOLS:
                os.unlink("%s%s.py" % (name, CMD_SUFFIX))
    else:
        setup(**setup_kwargs)
