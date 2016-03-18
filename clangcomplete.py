#!/usr/bin/env python
#
# Copyright (C) 2016 Martin Willi
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See <http://www.fsf.org/copyleft/gpl.txt>.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.

import os, subprocess, shlex
from clang.cindex import TranslationUnit, Index
from gi.repository import GObject, Gtk, Gedit, GtkSource

class ClangCompletionProvider(GObject.Object, GtkSource.CompletionProvider):
	__gtype_name__ = 'ClangCompletionProvider'

	def __init__(self, window):
		GObject.Object.__init__(self)
		self.window = window
		self.index = Index.create()
		self.completions = None
		self.line = 0
		self.token = None
		self.doc = None
		self.resource_dir = None

	def _get_buffer(self, context):
		return context.get_iter()[1].get_buffer()

	def _get_pos(self, buf):
		pos = buf.get_iter_at_offset(buf.get_property('cursor-position'))
		return pos.get_line() + 1, pos.get_line_offset() + 1

	def _get_token_before_iter(self, end):
		buf = end.get_buffer()
		start = buf.get_iter_at_offset(end.get_offset())
		start.set_line_offset(0)
		line = buf.get_text(start, end, False)
		if line.endswith('.') or line.endswith('->'):
			return ''
		tlen = 0
		for c in reversed(line):
			if c.isalnum() or c == '_':
				tlen = tlen + 1
			else:
				break
		if tlen == 0:
			return None
		return line[len(line) - tlen:]

	def _get_token(self, context):
		buf = self._get_buffer(context)
		end = context.get_iter()[1]
		return self._get_token_before_iter(end)

	def _get_doc(self):
		doc = self.window.get_active_document()
		if doc:
			loc = doc.get_location()
			if loc:
				return loc.get_path()
		return None

	def _get_docdir(self):
		path = self._get_doc()
		if path:
			return os.path.dirname(path)
		return None

	def _find_makefile(self):
		docdir = self._get_docdir()
		while docdir:
			makefile = os.path.join(docdir, 'Makefile')
			if os.path.isfile(makefile):
				return makefile
			if os.path.dirname(docdir) == docdir:
				return None
			docdir = os.path.dirname(docdir)
		return None

	def _cd_builddir(self):
		makefile = self._find_makefile()
		if makefile:
			os.chdir(os.path.dirname(makefile))

	def _add_cwd_include(self, args):
		docdir = self._get_docdir()
		if docdir:
			args.append("-I{}".format(docdir))

	def _get_clang_resource_dir(self):
		pipe = subprocess.PIPE
		clang = subprocess.Popen(['clang', '-###', '-E', '-'],
								stdout=pipe, stdin=pipe, stderr=pipe)
		out = clang.communicate(input=''.encode('utf-8'))[1].decode('utf-8')
		for line in out.split('\n'):
			if len(line) != 0:
				match = False
				for arg in shlex.split(line):
					if match:
						self.resource_dir = "-I{}/include".format(arg)
						return True
					if arg == '-resource-dir':
						match = True
		return False

	def _add_clang_resource_dir(self, args):
		if self.resource_dir or self._get_clang_resource_dir():
			args.append(self.resource_dir)

	def _add_make_cflags(self, args):
		makefile = self._find_makefile()
		if makefile:
			pipe = subprocess.PIPE
			make = subprocess.Popen(['make', '-f', makefile, '-f', '-',
									 'print-CFLAGS', 'print-CPPFLAGS',
									 'print-AM_CFLAGS', 'print-AM_CPPFLAGS'],
									stdout=pipe, stdin=pipe, stderr=pipe)
			printer = 'print-%:\n\t@echo \'$*=$($*)\'\n'.encode('utf-8')
			out = make.communicate(input=printer)[0].decode('utf-8')
			for line in out.split('\n'):
				if len(line) != 0:
					for arg in shlex.split(line[line.index('=') + 1:]):
						args.append(arg)

	def _get_completion_args(self, context):
		args = []
		self._add_clang_resource_dir(args)
		self._add_cwd_include(args)
		self._add_make_cflags(args)
		return args

	def _get_completion_path(self):
		path = self._get_doc()
		if (path):
			return os.path.relpath(path, os.getcwd())
		return None

	def _can_complete(self, context):
		lang = self._get_buffer(context).get_language()
		if lang:
			if lang.get_id() == 'c':
				return True
		return False

	def _get_completions(self, context, token):
		PRECOMPILED_PREAMBLE = 4
		if not self._can_complete(context):
			return []
		buf = self._get_buffer(context)
		line, column = self._get_pos(buf)
		column -= len(token)

		cwd = os.getcwd()
		self._cd_builddir()
		path = self._get_completion_path()
		args = self._get_completion_args(context)
		src = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
		files = [(path, src)]
		tu = TranslationUnit.from_source(path, args, unsaved_files=files,
										 options=PRECOMPILED_PREAMBLE,
										 index=self.index)
		cr = tu.codeComplete(path, line, column, unsaved_files=files,
							 include_macros=True, include_code_patterns=True)
		os.chdir(cwd)

		for d in cr.diagnostics:
			if d.severity >= 3:
				l = d.location
				print("{}:{}:{}: {}".format(l.file, l.line, l.column, d.spelling))
			if d.location.file == None:
				break

		completions = []
		for result in cr.results:
			hint = ''
			contents = ''
			for chunk in result.string:
				s = chunk.spelling
				if chunk.isKindTypedText():
					trigger = s
				hint += s
				if chunk.isKindResultType():
					hint += ' '
				else:
					contents += s
			if len(trigger) and len(hint):
				completions.append((trigger, hint, contents))
		return completions

	def do_get_name(self):
		return _('clang completion')

	def do_match(self, context):
		return self._can_complete(context)

	def _get_cached_completions(self, context, token):
		if self.completions:
			doc = self._get_doc()
			line, column = self._get_pos(self._get_buffer(context))
			if doc == self.doc and line == self.line and \
			   len(token) > 0 and token.startswith(self.token):
				return self.completions
			self.doc = doc
			self.line = line
			self.token = token
		self.completions = self._get_completions(context, token)
		return self.completions

	def do_populate(self, context):
		token = self._get_token(context)
		proposals = []
		if token != None:
			completions = self._get_cached_completions(context, token)
			for (trigger, hint, contents) in completions:
				if len(token) == 0 or trigger.startswith(token):
					item = GtkSource.CompletionItem.new(hint, contents, None, None)
					proposals.append(item)
		context.add_proposals(self, proposals, True)

	def do_get_activation(self):
		return GtkSource.CompletionActivation.INTERACTIVE # USER_REQUESTED

	def do_activate_proposal(self, proposal, end):
		token = self._get_token_before_iter(end)
		if token:
			buf = end.get_buffer()
			start = buf.get_iter_at_offset(end.get_offset())
			start.set_line_offset(end.get_line_offset() - len(token))
			buf.delete(start, end)
			text = proposal.get_text()
			buf.insert(end, text)
			if text[-1] == ')' and '(' in text:
				start = buf.get_iter_at_offset(end.get_offset())
				start.set_line_offset(end.get_line_offset() -
									  len(text) + text.index('(') + 1)
				buf.select_range(start, end)
			return True
		return False

	def do_get_priority(self):
		return 100

class ClangCompletion(GObject.Object, Gedit.WindowActivatable):
	__gtype_name__ = 'ClangCompletion'
	window = GObject.property(type=Gedit.Window)
	providers = {}

	def __init__(self):
		GObject.Object.__init__(self)

	def do_update_state(self):
		for view in self.window.get_views():
			if view not in self.providers:
				provider = ClangCompletionProvider(self.window)
				view.get_completion().add_provider(provider)
				self.providers[view] = provider
		for view, provider in self.providers.items():
			if view not in self.window.get_views():
				if provider in view.get_completion().get_providers():
					view.get_completion().remove_provider(provider)
				del self.providers[view]
				break

	def do_activate(self):
		self.do_update_state()

	def do_deactivate(self):
		self.do_update_state()
