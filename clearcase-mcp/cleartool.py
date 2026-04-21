""" Modules to interact with a cleartool command line """

# Licensed Materials - Property of HCL
# (C) Copyright HCL Technologies Ltd. 2024, 2026.  All Rights Reserved.
# Note to U.S. Government Users Restricted Rights:
# Use, duplication or disclosure restricted by GSA ADP Schedule Contract

import platform
import os
import subprocess
import logging
from process import Process
import configparser

WINDOWS_OS = "Windows"
platform_name = platform.system()

# Class to interact with a 'cleartool' command execution


class Cleartool(Process):
    """Cleartool process"""

    def __init__(self, user=None):
        self._logger = logging.getLogger(__name__)
        self._path = self.find_executable()
        super().__init__(user)

    # returns the error output
    def error(self):
        return self._stderr

    # returns the standard output
    def output(self):
        return self._stdout

    # Find a valid cleartool executable; defer to CLEARCASE_HOME if set
    def find_executable(self):
        """find a cleartool executable to use"""
        if platform_name == WINDOWS_OS:
            pathList = [r"C:\Program Files\DevOps\Code\ClearCase\bin"]
            cc_str = "cleartool.exe"
        else:
            pathList = ["/usr/atria/bin", "/opt/devops/code/clearcase/bin"]
            cc_str = "cleartool"

        config = configparser.ConfigParser()

        """Check if there's a config.ini file"""
        server_dir = os.path.dirname(os.path.abspath(__file__))
        file_to_read = server_dir + os.sep + "config.ini"
        config.read(file_to_read)
        try:
            cfg_ct_path = config.get('ClearCase', 'path')
        except Exception as e:
            """Use the EV or the defaults"""
            pass
        else:
            if os.path.exists(cfg_ct_path):
                ct_path = cfg_ct_path + os.sep + cc_str
                if os.path.exists(ct_path):
                    return ct_path 

        """Check for the EV"""
        path = os.getenv("CLEARCASE_HOME")
        if path:
            return path + os.sep + cc_str

        """Use the defaults"""
        for path in pathList:
            ct_path = path + os.sep + cc_str
            if os.path.exists(ct_path):
                return ct_path

    # Run the specified cleartool subcommand
    def run(self, args, cd_path=None):
        self._logger.debug("COMMAND: %s", " ".join(args))
        self._logger.debug("CLEARTOOL_PATH: %s", self._path)

        if cd_path is not None:
            args_str = " ".join(args)
            super().run([self._path + " " + args_str], cd_path, stdin=subprocess.DEVNULL)
        else:
            super().run([self._path] + args, stdin=subprocess.DEVNULL)
        self._logger.debug("CLEARTOOL_PATH: %s", self._path)
        self._logger.debug("STDOUT: %s", self._stdout)
        self._logger.debug("STDERR: %s", self._stderr)
