# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: t -*-
# vi: set ft=python sts=4 ts=4 sw=4 noet :

# This file is part of Fail2Ban.
#
# Fail2Ban is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Fail2Ban is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Fail2Ban; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Author: Cyril Jaquier
# Modified by: Yaroslav Halchenko (SafeConfigParserWithIncludes)

__author__ = "Cyril Jaquier"
__copyright__ = "Copyright (c) 2004 Cyril Jaquier"
__license__ = "GPL"

import glob, os
from ConfigParser import NoOptionError, NoSectionError

from .configparserinc import SafeConfigParserWithIncludes
from ..helpers import getLogger

# Gets the instance of the logger.
logSys = getLogger(__name__)
_logLevel = 6

class ConfigReader():
	"""Generic config reader class.

  A caching adapter which automatically reuses already shared configuration.
			 """

	def __init__(self, use_config=None, share_config=None, **kwargs):
		# use given shared config if possible (see read):
		self._cfg_share = None
		self._cfg = None
		if use_config is not None:
			self._cfg = use_config
		else:
			# share config if possible:
			if share_config is not None:
				self._cfg_share = share_config
				self._cfg_share_kwargs = kwargs
			else:
				self._cfg = ConfigReaderUnshared(**kwargs)

	def setBaseDir(self, basedir):
		self._cfg.setBaseDir(basedir)

	def getBaseDir(self):
		return self._cfg.getBaseDir()

	def read(self, name, once=True):
		# shared ?
		if not self._cfg and self._cfg_share is not None:
			self._cfg = self._cfg_share.get(name)
			if not self._cfg:
				self._cfg = ConfigReaderUnshared(**self._cfg_share_kwargs)
				self._cfg_share[name] = self._cfg
		# performance feature - read once if using shared config reader:
		rc = self._cfg.read_cfg_files
		if once and rc.get(name) is not None:
			return rc.get(name)

		# read:
		ret = self._cfg.read(name)

		# save already read:
		if once:
			rc[name] = ret
		return ret

	def sections(self):
		return self._cfg.sections()

	def has_section(self, sec):
		return self._cfg.has_section(sec)

	def options(self, *args):
		return self._cfg.options(*args)

	def get(self, sec, opt):
		return self._cfg.get(sec, opt)

	def getOptions(self, *args, **kwargs):
		return self._cfg.getOptions(*args, **kwargs)


class ConfigReaderUnshared(SafeConfigParserWithIncludes):
	"""Unshared config reader (previously ConfigReader).

	Does not use this class (internal not shared/cached represenation).
	Use ConfigReader instead.
			 """

	DEFAULT_BASEDIR = '/etc/fail2ban'
	
	def __init__(self, basedir=None):
		SafeConfigParserWithIncludes.__init__(self)
		self.read_cfg_files = dict()
		self.setBaseDir(basedir)
	
	def setBaseDir(self, basedir):
		if basedir is None:
			basedir = ConfigReaderUnshared.DEFAULT_BASEDIR	# stock system location
		self._basedir = basedir.rstrip('/')
	
	def getBaseDir(self):
		return self._basedir
	
	def read(self, filename):
		if not os.path.exists(self._basedir):
			raise ValueError("Base configuration directory %s does not exist "
							  % self._basedir)
		basename = os.path.join(self._basedir, filename)
		logSys.debug("Reading configs for %s under %s " , filename, self._basedir)
		config_files = [ basename + ".conf" ]

		# possible further customizations under a .conf.d directory
		config_dir = basename + '.d'
		config_files += sorted(glob.glob('%s/*.conf' % config_dir))

		config_files.append(basename + ".local")
	
		config_files += sorted(glob.glob('%s/*.local' % config_dir))

		# choose only existing ones
		config_files = filter(os.path.exists, config_files)

		if len(config_files):
			# at least one config exists and accessible
			logSys.debug("Reading config files: %s", ', '.join(config_files))
			config_files_read = SafeConfigParserWithIncludes.read(self, config_files,
				log_info=("Cache configs for %s under %s " , filename, self._basedir))
			missed = [ cf for cf in config_files if cf not in config_files_read ]
			if missed:
				logSys.error("Could not read config files: %s", ', '.join(missed))
			if config_files_read:
				return True
			logSys.error("Found no accessible config files for %r under %s",
						 ( filename, self.getBaseDir() ))
			return False
		else:
			logSys.error("Found no accessible config files for %r " % filename
						 + (["under %s" % self.getBaseDir(),
							 "among existing ones: " + ', '.join(config_files)][bool(len(config_files))]))

			return False

	##
	# Read the options.
	#
	# Read the given option in the configuration file. Default values
	# are used...
	# Each optionValues entry is composed of an array with:
	# 0 -> the type of the option
	# 1 -> the name of the option
	# 2 -> the default value for the option
	
	def getOptions(self, sec, options, pOptions = None):
		values = dict()
		for option in options:
			try:
				if option[0] == "bool":
					v = self.getboolean(sec, option[1])
				elif option[0] == "int":
					v = self.getint(sec, option[1])
				else:
					v = self.get(sec, option[1])
				if not pOptions is None and option[1] in pOptions:
					continue
				values[option[1]] = v
			except NoSectionError, e:
				# No "Definition" section or wrong basedir
				logSys.error(e)
				values[option[1]] = option[2]
				# TODO: validate error handling here.
			except NoOptionError:
				if not option[2] is None:
					logSys.warning("'%s' not defined in '%s'. Using default one: %r"
								% (option[1], sec, option[2]))
					values[option[1]] = option[2]
				elif logSys.getEffectiveLevel() <= _logLevel:
					logSys.log(_logLevel, "Non essential option '%s' not defined in '%s'.", option[1], sec)
			except ValueError:
				logSys.warning("Wrong value for '" + option[1] + "' in '" + sec +
							"'. Using default one: '" + `option[2]` + "'")
				values[option[1]] = option[2]
		return values

class DefinitionInitConfigReader(ConfigReader):
	"""Config reader for files with options grouped in [Definition] and
       [Init] sections.

       Is a base class for readers of filters and actions, where definitions
       in jails might provide custom values for options defined in [Init]
       section.
       """

	_configOpts = []
	
	def __init__(self, file_, jailName, initOpts, **kwargs):
		ConfigReader.__init__(self, **kwargs)
		self.setFile(file_)
		self.setJailName(jailName)
		self._initOpts = initOpts
	
	def setFile(self, fileName):
		self._file = fileName
		self._initOpts = {}
	
	def getFile(self):
		return self._file
	
	def setJailName(self, jailName):
		self._jailName = jailName
	
	def getJailName(self):
		return self._jailName
	
	def read(self):
		return ConfigReader.read(self, self._file)

	# needed for fail2ban-regex that doesn't need fancy directories
	def readexplicit(self):
		return SafeConfigParserWithIncludes.read(self, self._file)
	
	def getOptions(self, pOpts):
		self._opts = ConfigReader.getOptions(
			self, "Definition", self._configOpts, pOpts)
		
		if self.has_section("Init"):
			for opt in self.options("Init"):
				if not self._initOpts.has_key(opt):
					self._initOpts[opt] = self.get("Init", opt)
	
	def convert(self):
		raise NotImplementedError
