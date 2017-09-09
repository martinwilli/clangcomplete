# Gedit plugin providing libclang based autocompletion suggestions #

This Python based gedit plugin implements autocompletion using LLVMs libclang.
It currently supports the C language only.

## Installation ##

The plugin requires libclang and its Python bindings for the Python version
gedit uses, usually Python 3. LLVM 5 is known to work, and it finally comes
with clang bindings for Python 3. _https://apt.llvm.org_ provides Debian/Ubuntu
packages, but unfortunately _python-clang-5.0_ is for Python 2; one may move
that packages files to a Python 3 site, though.

Please note that your Python libclang binding might require a specific
libclang-v.x.so.y library name it tries to dlopen(). Just create an appropriate
symlink (in Ubuntu/x64 under /usr/lib/x86_64-linux-gnu/) until we have some
support to find installed libclang libraries.

To install the plugin itself, copy both the _clangcomplete.plugin_ and
_clangcomplete.py_ files to _~/.local/share/gedit/plugins/_.

## C build environment ##

To allow clang to process your sources for completion suggestions, it must
reuse the environment that your build system usually would use. For a simple
project that is not much of a problem, but for lager projects, where
autocompletion really shines, this gets more complex. The plugin can currently
handle automake based projects.

### Automake build environment ###

When feeding a source file to libclang, the plugin first tries to find a
Makefile in the local or any parent directory of the source file. It uses
the directory of such a file as working dir when feeding the sources to
libclang. Then it uses _make_ to read some CPPFLAGS and CFLAGS from the
Makefile, and uses these flags when processing the sources. This should make
clang aware of any include directorories or defines that your build system
requires.

## Issues ##

Depending on the include structure of your project, things _might... get...
slow..._ when typing. The plugin uses some minimal caching, but this
certainly can be improved. If it gets too slow in your project, you
may change the plugin to use GtkSource.CompletionActivation.USER_REQUESTED.
Then you'll explicitly have to hit CTRL+Space to get suggestions.
