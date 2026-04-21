""" class to manage a subprocess """

# Licensed Materials - Property of HCL
# (C) Copyright HCL Technologies Ltd. 2024, 2025.  All Rights Reserved.
# Note to U.S. Government Users Restricted Rights:
# Use, duplication or disclosure restricted by GSA ADP Schedule Contract

import subprocess
import platform
import logging

WINDOWS_OS = "Windows"


class Process:
    """class to manage a subprocess"""

    def __init__(self, user=None):
        self._stdout = None
        self._stderr = None
        self._returncode = None
        self._args = None
        self._user = user

    def run(self, args, cd_path=None, stdin=None):
        platform_name = platform.system()
        self._StdOut = None
        self._StdErr = None
        self._ReturnCode = None
        try:
            completed_process = subprocess.run(
                args, capture_output=True, universal_newlines=True, check=False, stdin=stdin
            )
            self._stdout = completed_process.stdout
            self._returncode = completed_process.returncode
            self._stderr = completed_process.stderr
            logging.error(self._stderr)
        except subprocess.CalledProcessError as e:
            logging.error("Error " + e + " executing command: " + " ".join(map(str, args)))

    def output(self):
        """return stdout from the process"""
        return self._stdout

    def error(self):
        """return stderr from the process"""
        return self._stderr

    def returnCode(self):
        """return code from the process"""
        return self._returncode

    def dump(self):
        """for debugging, output everything"""
        logging.info("_args: " + " ".join(self._args))
        logging.info("_stdout: " + self._stdout)
        logging.info("_stderr: " + self._stderr)
        logging.info("_returncode: " + str(self._returncode))
