"""uv run mcp run clearcase-mcp.py"""

# Licensed Materials - Property of HCL
# (C) Copyright HCL Technologies Ltd. 2025, 2026.  All Rights Reserved.
# Note to U.S. Government Users Restricted Rights:
# Use, duplication or disclosure restricted by GSA ADP Schedule Contract

from mcp.server.fastmcp import FastMCP, Context
import subprocess
import platform
import os
import re
import time
import logging
import socket
from process import Process
import cleartool
from collections import OrderedDict
from pathlib import Path

# Create the MCP server
mcp = FastMCP("ClearCase MCP server")

WINDOWS_OS = "Windows"
platform_name = platform.system()
hostname = socket.gethostname()
ALLOWED_CMDS = ["mkvob", "lsvob", "lsview", "lstype", "checkout", "lscheckout", "uncheckout", "checkin", "describe", "rebase", "deliver", "setactivity", "chactivity", "chstream", "mkbl", "lsbl", "lsprovider", "lstask", "settask", "chtask", "lshistory"]
CMDS_REQ_COMMENT = ["mkvob", "checkout", "checkin", "setactivity", "chactivity", "chstream", "mkbl"]

logger = logging.getLogger(__name__)
logging.basicConfig(filename='clearcase-mcp.log',
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# HELPER FUNCTIONS
# Run a cleartool subcommand
def run_cleartool(args):
    """Run a cleartool command"""
    ct = cleartool.Cleartool()
    ct.run(args)
    logging.info("Ran args[0]: '%s'", ct.output())
    return ct.output(), ct.error(), ct.returnCode()

# Register MCP Tools
# Tool to list the ClearCase version on this host
@mcp.tool(
    annotations={
        "title": "List the ClearCase version",
        "readOnlyHint": True
    }
)
def ls_verall():
    """Get the ClearCase version installed on the local host"""
    args = ["-verAll"]
    cmdOut, cmdErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran -verAll: '%s'", cmdOut)
    else:
        logging.error("Error running -verAll: '%s'", cmdOut)
    return cmdOut, cmdErr, status

# Tool to list views
@mcp.tool(
    annotations={
        "title": "List ClearCase views",
        "readOnlyHint": True
    }
)
def list_views_by_pattern(viewtag_pattern=None):
    """List one or all ClearCase views"""
    args = ["lsview"]
    if viewtag_pattern != None:
        args.append(viewtag_pattern)
    lsViewOut, lsViewErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran lsview: '%s'", lsViewOut)
    else:
        logging.error("Error running lsview: '%s' with status '%d'", lsViewOut)
    return lsViewOut, lsViewErr, status

# Tool to run cleartool lstype -kind <type> -invob <vobtag>
@mcp.tool(
    annotations={
        "title": "List objects of a type in a VOB",
        "readOnlyHint": True
    }
)
def list_objs_of_type(object_type, vobtag):
    """List objects of a type in a VOB"""
    args = ["lstype", "-kind", object_type, "-invob", vobtag]
    lsTypeOut, lsTypeErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran lstype: '%s'", lsTypeOut)
    else:
        logging.error("Error running lstype: '%s' with status '%d'", lsTypeOut, status)
    return lsTypeOut, lsTypeErr, status

# Tool to list a stream associated with a view
@mcp.tool(
    annotations={
        "title": "List the stream associated with a view",
        "readOnlyHint": True
    }
)
def lsstream_on_view(view_tag: str):
    """Get the stream associated with this view"""
    args = ["lsstream", "-fmt", "%Xn", "-view", view_tag]
    cmdOut, cmdErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran lsstream: '%s'", cmdOut)
    else:
        logging.error("Error running lsstream: '%s'", cmdOut)
        if not cmdOut:
            logging.info("View '$\%s' is not associated with a stream", view_tag)
            cmdOut += "View not associated with a stream"
    return cmdOut, cmdErr, status

# Tool to list activities associated with a view
@mcp.tool(
    annotations={
        "title": "List the activities associated with a view",
        "readOnlyHint": True
    }
)
def lsact_on_view(view_tag: str):
    """Get the activities associated with a view"""
    args = ["lsact", "-view", view_tag]
    cmdOut, cmdErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran lsact: '%s'", cmdOut)
    else:
        logging.error("Error running lsact: '%s'", cmdOut)
    return cmdOut, cmdErr, status

# Tool to set an activity a view
@mcp.tool(
    annotations={
        "title": "Set an activity in a view",
    }
)
def setact_on_view(view_tag: str, activity=None, comment=None):
    """Set the activity associated with this view"""
    args = ["setact", "-view", view_tag]
    if comment == None:
        args.append("-nc")
    else:
        args.append("-c")
        args.append(comment)
    if (activity == None) or (activity == ""):
        args.append("-none")
    else:
        args.append(activity)
    cmdOut, cmdErr, status = run_cleartool(args)
    if status == 0:
        logging.info("Ran setact: '%s'", cmdOut)
    else:
        logging.error("Error running setact: '%s'", cmdOut)
    return cmdOut, cmdErr, status

# run_cleartool tool
@mcp.tool(
    annotations={
        "title": "Run a cleartool subcommand"
    }
)
def run_cleartool_cmd(in_str):
    """Run a cleartool subcommand from a string"""
    opts = in_str.split(" ")
    myOp = opts.pop(0)
    if myOp not in ALLOWED_CMDS:
        logging.error("Operation '%s' is not allowed", myOp)
        return "", "Error: operation not allowed", 1
    myArg = myOp.strip()
    args = []
    args.append(myArg)
    """Parse opts list"""
    QT = "\""
    SP = " "
    inQT = False
    myTmpStr = ""
    if len(opts) >= 1:
        for myItem in opts:
            if QT not in myItem:
                if not inQT:
                    """Not in quotes, safe to add"""
                    myOpt = myItem.strip()
                    args.append(myOpt)
                else:
                    """Part of quoted text, add to a tmp string"""
                    myTmpStr += SP + myItem
            else:
                """Determine if this is an opening or closing quote"""
                if not inQT:
                    """Assume we're opening a quote"""
                    inQT = True
                    myTmpStr = myItem.removeprefix(QT)
                else:
                    """Assume we're closing a quote"""
                    args.append(myTmpStr + SP + myItem.removesuffix(QT))
                    inQT = False
                    myTmpStr = ""
                                        
    """Prevent hangs in subcommands"""
    if myArg in CMDS_REQ_COMMENT:
        if "-c" not in args and "-comment" not in args and "-nc" not in args:
            args.insert(1, "-nc")
    if "uncheckout" in myArg:
        if "-keep" not in args and "-rm" not in args:
            args.insert(1, "-keep")
    if "rebase" in myArg:
        if "-graphical" in args:
            logging.error("Option -graphical is not allowed for operation '%s'", myOp)
            return "", "Error: option not allowed", 1
        if "-gmerge" in args:
            logging.error("Option -gmerge is not allowed for operation '%s'", myOp)
            return "", "Error: option not allowed", 1
        if "-preview" not in args:
            if "-recommended" in args or "-resume" in args or "-complete" in args:
                if "-abort" not in args:
                    args.insert(1, "-abort")
        if "-cancel" in args:
            if "-force" not in args:
                args.insert(1, "-force")
    if "deliver" in myArg:
        if "-graphical" in args:
            logging.error("Option -graphical is not allowed for operation '%s'", myOp)
            return "", "Error: option not allowed", 1
        if "-gmerge" in args:
            logging.error("Option -gmerge is not allowed for operation '%s'", myOp)
            return "", "Error: option not allowed", 1
        """For -status and -preview do not add -abort or -force"""
        if "-status" not in args and "-preview" not in args:
            if "-abort" not in args:
                args.insert(1, "-abort")
            if "-force" not in args:
                args.insert(1, "-force")
    ct = cleartool.Cleartool()
    ct.run(args)
    logging.info("Ran args[0]: '%s'", ct.output())
    return ct.output(), ct.error(), ct.returnCode()

# Define MCP Resources
# Resource to return rebase tips
@mcp.resource("resource://rebase_tips")
def rebase_tips() -> str:
    """Return tips for successful rebase"""
    return "Make sure your directories and files are checked in"

# Define MCP Prompts
# Add a mkact prompt
@mcp.prompt()
def make_cleartool_activity(activity_name: str, headline: str, view_tag: str, cmi_tasks=None, comment=None) -> str:
    """Run cleartool mkactivity"""
    lsStreamArgs = ["lsstream", "-fmt", "%Xn", "-view", view_tag]
    lsOut, lsErr, lsStatus = run_cleartool(lsStreamArgs)
    if lsStatus != 0:
        logging.error("Error running lsstream: '%s' with status '%d'", lsOut, lsStatus)
        return lsOut, lsErr, lsStatus
    else:
        streamName = lsOut
        AT = "@"
        (stream, vobtag) = lsOut.split(AT, 1)
        act_name = AT.join([activity_name, vobtag])
        if comment == None:
            mkactArgs = ["mkactivity", "-nc", "-headline", headline, "-in", streamName]
        else:
            mkactArgs = ["mkactivity", "-comment", comment, "-headline", headline, "-in", streamName]
        if cmi_tasks != None:
            mkactArgs.append("-tasks")
            mkactArgs.append(cmi_tasks)
        mkactArgs.append(act_name)
            
        mkactOut, mkactErr, status = run_cleartool(mkactArgs)
        if status == 0:
            logging.info("Ran mkactivity: '%s'", mkactOut)
        else: 
            logging.error("Error running mkactivity: '%s' with status '%d'", mkactOut, status)
        return mkactOut, mkactErr, status
    
# Developer prompt for daily view setup
@mcp.prompt()
def daily_view_setup(view_tag: str, activity_to_work_on=None) -> str:
    """Rebase the stream attached to this view"""
    setupErr = ""
    setupStatus = 0
    lsStreamArgs = ["lsstream", "-fmt", "%Xn", "-view", view_tag]
    lsOut, lsErr, lsStatus = run_cleartool(lsStreamArgs)
    if lsStatus != 0:
        return lsOut, lsErr, lsStatus
    else:
        """Try to rebase the stream"""
        streamName = lsOut
        beginRebaseArgs = ["rebase", "-recommended", "-complete", "-force", "-abort", "-stream", streamName]
        beginOut, beginErr, beginStatus = run_cleartool(beginRebaseArgs)
        if "No rebase needed" in beginOut:
            logging.info(beginOut)
        if "No Automatic Decision Possible" in beginOut:
            logging.info("Nontrivial merge detected, will cancel rebase")
            cancelRebaseArgs = ["rebase", "-cancel", "-force", "-stream", streamName]
            cancelOut, cancelErr, cancelStatus = run_cleartool(cancelRebaseArgs)
            if "Rebase canceled" in cancelOut:
                setupOut = "Unable to automatically rebase your stream, please rebase it manually to deal with potential merge conflicts"
                return setupOut, setupErr, setupStatus
            else:
                return cancelOut, cancelErr, cancelStatus 
        else:
            if beginStatus != 0:
                return beginOut, beginErr, beginStatus
        if activity_to_work_on != None:
            setOut, setErr, setStatus = setact_on_view(view_tag, activity_to_work_on, "Setting activity " + activity_to_work_on + " as part of daily_view_setup")
            logging.info(setOut)
            if setStatus != 0:
                return setOut, setErr, setStatus
            else:
                setupOut = "Your stream is ready to work on " + activity_to_work_on
        else:
            setupOut = "Your stream is ready, select an existing activity or create a new activity to work on"
        return setupOut, setupErr, setupStatus
            
    
if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')
