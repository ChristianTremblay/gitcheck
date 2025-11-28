#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import getopt
import time
import subprocess
from subprocess import PIPE
import smtplib
from smtplib import SMTPException
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import shlex
from os.path import expanduser
from time import strftime
import json

from rich.console import Console

console = Console()

# Global vars
argopts = {}
colortheme = None
#Load custom parameters from ~/mygitcheck.py
configfile = expanduser('~/mygitcheck.py')
if os.path.exists(configfile):
    sys.path.append(expanduser('~'))
    import mygitcheck as userconf

    # Try to load colortheme
    if hasattr(userconf, 'colortheme'):
        colortheme = userconf.colortheme
if colortheme is None:
    # Default theme using rich colors
    colortheme = {
        'default': 'white',
        'prjchanged': 'bold deep_pink1',
        'prjremote': 'magenta',
        'prjname': 'chartreuse1',
        'reponame': 'light_goldenrod2',
        'branchname': 'white',
        'fileupdated': 'light_goldenrod2',
        'remoteto': 'deep_sky_blue3',
        'committo': 'violet',
        'commitinfo': 'deep_sky_blue3',
        'commitstate': 'deep_pink1',
    }


class html:
    msg = "<ul>\n"
    topull = ""
    topush = ""
    strlocal = ""
    prjname = ""
    path = ""
    timestamp = ""


def showDebug(mess, level='info'):
    if argopts.get('debugmod', False):
        console.print(f"[dim]{mess}[/dim]")


# Search all local repositories from current directory
def searchRepositories():
    showDebug('Beginning scan... building list of git folders')
    dirs = argopts.get('searchDir', [os.path.abspath(os.getcwd())])
    repo = set()
    for curdir in dirs:
        if curdir[-1:] == '/':
            curdir = curdir[:-1]
        showDebug("  Scan git repositories from %s" % curdir)

        html.path = curdir
        startinglevel = curdir.count(os.sep)

        for directory, dirnames, filenames in os.walk(curdir):
            level = directory.count(os.sep) - startinglevel
            if argopts.get('depth', None) is None or level <= argopts.get('depth', None):
                if '.git' in dirnames:
                    showDebug("  Add %s repository" % directory)
                    repo.add(directory)

    showDebug('Done')
    return sorted(repo)


# Check state of a git repository
def checkRepository(rep, branch):
    aitem = []
    mitem = []
    ditem = []
    gsearch = re.compile(r'^.?([A-Z]) (.*)')

    if re.match(argopts.get('ignoreBranch', r'^$'), branch):
        return False

    changes = getLocalFilesChange(rep)
    ischange = len(changes) > 0
    actionNeeded = False  # actionNeeded is branch push/pull, not local file change.

    topush = ""
    topull = ""
    html.topush = ""
    html.topull = ""
    if branch != "":
        remotes = getRemoteRepositories(rep)
        hasremotes = bool(remotes)
        for r in remotes:
            count = len(getLocalToPush(rep, r, branch))
            ischange = ischange or (count > 0)
            actionNeeded = actionNeeded or (count > 0)
            if count > 0:
                topush += f" [{colortheme['reponame']}]{r}[/][[{colortheme['remoteto']}]To Push:[/]{count}]"
                html.topush += '<b style="color:black">%s</b>[<b style="color:blue">To Push:</b><b style="color:black">%s</b>]' % (
                    r,
                    count
                )

        for r in remotes:
            count = len(getRemoteToPull(rep, r, branch))
            ischange = ischange or (count > 0)
            actionNeeded = actionNeeded or (count > 0)
            if count > 0:
                topull += f" [{colortheme['reponame']}]{r}[/][[{colortheme['remoteto']}]To Pull:[/]{count}]"
                html.topull += '<b style="color:black">%s</b>[<b style="color:blue">To Pull:</b><b style="color:black">%s</b>]' % (
                    r,
                    count
                )
    if ischange or not argopts.get('quiet', False):
        # Remove trailing slash from repository/directory name
        if rep[-1:] == '/':
            rep = rep[:-1]

        # Do some magic to not show the absolute path as repository name
        # Case 1: script was started in a directory that is a git repo
        if rep == os.path.abspath(os.getcwd()):
            (head, tail) = os.path.split(rep)
            if tail != '':
                repname = tail
        # Case 2: script was started in a directory with possible subdirs that contain git repos
        elif rep.find(os.path.abspath(os.getcwd())) == 0:
            repname = rep[len(os.path.abspath(os.getcwd())) + 1:]
        # Case 3: script was started with -d and above cases do not apply
        else:
            repname = rep

        if ischange:
            prjname = "%s%s%s" % (colortheme['prjchanged'], repname, colortheme['default'])
            html.prjname = '<b style="color:red">%s</b>' % (repname)
        elif not hasremotes:
            prjname = "%s%s%s" % (colortheme['prjremote'], repname, colortheme['default'])
            html.prjname = '<b style="color:magenta">%s</b>' % (repname)
        else:
            prjname = "%s%s%s" % (colortheme['prjname'], repname, colortheme['default'])
            html.prjname = '<b style="color:green">%s</b>' % (repname)

        # Print result
        if len(changes) > 0:
            lenFilesChanged = len(getLocalFilesChange(rep))
            strlocal = f"[{colortheme['reponame']}]Local[/][[{colortheme['remoteto']}]To Commit:[/]{lenFilesChanged}]"
            html.strlocal = '<b style="color:orange"> Local</b><b style="color:black">['
            html.strlocal += "To Commit:%s" % (
                lenFilesChanged
            )
            html.strlocal += "]</b>"
        else:
            strlocal = ""
            html.strlocal = ""

        if argopts.get('email', False):
            html.msg += "<li>%s/%s %s %s %s</li>\n" % (html.prjname, branch, html.strlocal, html.topush, html.topull)

        else:
            cbranch = f"[{colortheme['branchname']}]{branch}[/]"
            prjname_styled = f"[{colortheme['prjname'] if not ischange else colortheme['prjchanged'] if hasremotes else colortheme['prjremote']}]{repname}[/]"
            console.print(f"{prjname_styled}/{cbranch} {strlocal}{topush}{topull}")

        if argopts.get('verbose', False):
            if ischange > 0:
                if not argopts.get('email', False):
                    console.print("  [bold]|--Local[/bold]")
                html.msg += '<ul><li><b>Local</b></li></ul>\n<ul>\n'
                for c in changes:
                    html.msg += '<li> <b style="color:orange">[To Commit] </b>%s</li>\n' % c[1]
                    if not argopts.get('email', False):
                        console.print(f"     |--[{colortheme['commitstate']}]{c[0]}[/] [{colortheme['fileupdated']}]{c[1]}[/]")
                html.msg += '</ul>\n'
            if branch != "":
                remotes = getRemoteRepositories(rep)
                for r in remotes:
                    commits = getLocalToPush(rep, r, branch)
                    if len(commits) > 0:
                        html.msg += '<ul><li><b>%(r)s</b></li>\n</ul>\n<ul>\n' % locals()
                        if not argopts.get('email', False):
                            console.print(f"  |--{r}")
                        for commit in commits:
                            html.msg += '<li><b style="color:blue">[To Push] </b>%s</li>\n' % commit
                            if not argopts.get('email', False):
                                console.print(f"     |--[{colortheme['committo']}][To Push][/] [{colortheme['commitinfo']}]{commit}[/]")
                        html.msg += '</ul>\n'

            if branch != "":
                remotes = getRemoteRepositories(rep)
                for r in remotes:
                    commits = getRemoteToPull(rep, r, branch)
                    if len(commits) > 0:
                        html.msg += '<ul><li><b>%(r)s</b></li>\n</ul>\n<ul>\n' % locals()
                        if not argopts.get('email', False):
                            console.print(f"  |--{r}")
                        for commit in commits:
                            html.msg += '<li><b style="color:blue">[To Pull] </b>%s</li>\n' % commit
                            if not argopts.get('email', False):
                                console.print(f"     |--[{colortheme['committo']}][To Pull][/] [{colortheme['commitinfo']}]{commit}[/]")
                        html.msg += '</ul>\n'

    return actionNeeded


def getLocalFilesChange(rep):
    files = []
    #curdir = os.path.abspath(os.getcwd())
    snbchange = re.compile(r'^(.{2}) (.*)')
    onlyTrackedArg = "" if argopts.get('checkUntracked', False) else "uno"
    result = gitExec(rep, "status -s" + onlyTrackedArg)

    lines = result.split('\n')
    for line in lines:
        if not re.match(argopts.get('ignoreLocal', r'^$'), line):
            m = snbchange.match(line)
            if m:
                files.append([m.group(1), m.group(2)])

    return files


def hasRemoteBranch(rep, remote, branch):
    result = gitExec(rep, 'branch -r')
    return '%s/%s' % (remote, branch) in result


def getLocalToPush(rep, remote, branch):
    if not hasRemoteBranch(rep, remote, branch):
        return []
    result = gitExec(rep, "log %(remote)s/%(branch)s..%(branch)s --oneline"
                     % locals())

    return [x for x in result.split('\n') if x]


def getRemoteToPull(rep, remote, branch):
    if not hasRemoteBranch(rep, remote, branch):
        return []
    result = gitExec(rep, "log %(branch)s..%(remote)s/%(branch)s --oneline"
                     % locals())

    return [x for x in result.split('\n') if x]


def updateRemote(rep):
    gitExec(rep, "remote update")


# Get Default branch for repository
def getDefaultBranch(rep):
    sbranch = re.compile(r'^\* (.*)', flags=re.MULTILINE)
    gitbranch = gitExec(rep, "branch"
                        % locals())

    branch = ""
    m = sbranch.search(gitbranch)
    if m:
        branch = m.group(1)

    return {branch}


# Get all branches for repository
def getAllBranches(rep):
    gitbranch = gitExec(rep, "branch"
                        % locals())

    branch = gitbranch.splitlines()

    return [b[2:] for b in branch]


def getRemoteRepositories(rep):
    result = gitExec(rep, "remote"
                     % locals())

    remotes = [x for x in result.split('\n') if x]
    return remotes


def gitExec(path, cmd):
    commandToExecute = "git -C \"%s\" %s" % (path, cmd)
    cmdargs = shlex.split(commandToExecute)
    showDebug("EXECUTE GIT COMMAND '%s'" % cmdargs)
    p = subprocess.Popen(cmdargs, stdout=PIPE, stderr=PIPE)
    output, errors = p.communicate()
    if p.returncode:
        console.print(f'[red]Failed running {commandToExecute}[/red]')
        raise Exception(errors)
    return output.decode('utf-8')


# Check all git repositories
def gitcheck():
    showDebug("Global Vars: %s" % argopts)

    repo = searchRepositories()
    actionNeeded = False

    if argopts.get('checkremote', False):
        for r in repo:
            console.print(f"[cyan]Updating {r} remotes...[/cyan]")
            updateRemote(r)

    if argopts.get('watchInterval', 0) > 0:
        console.clear()
        console.print(f"[bold]{strftime('%Y-%m-%d %H:%M:%S')}[/bold]")

    showDebug("Processing repositories... please wait.")
    for r in repo:
        if (argopts.get('checkall', False)):
            branch = getAllBranches(r)
        else:
            branch = getDefaultBranch(r)
        for b in branch:
            if checkRepository(r, b):
                actionNeeded = True
    html.timestamp = strftime("%Y-%m-%d %H:%M:%S")
    html.msg += "</ul>\n<p>Report created on %s</p>\n" % html.timestamp

    if actionNeeded and argopts.get('bellOnActionNeeded', False):
        console.bell()


def sendReport(content):
    userPath = expanduser('~')
    filepath = r'%s\Documents\.gitcheck' % userPath
    filename = filepath + "//mail.properties"
    config = json.load(open(filename))

    # Create message container - the correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Gitcheck Report (%s)" % (html.path)
    msg['From'] = config['from']
    msg['To'] = config['to']

    # Create the body of the message (a plain-text and an HTML version).
    text = "Gitcheck report for %s created on %s\n\n This file can be seen in html only." % (html.path, html.timestamp)
    htmlcontent = "<html>\n<head>\n<h1>Gitcheck Report</h1>\n<h2>%s</h2>\n</head>\n<body>\n<p>%s</p>\n</body>\n</html>" % (
        html.path, content
    )
    # Write html file to disk
    with open(filepath + '//result.html', 'w') as f:
        f.write(htmlcontent)
    console.print(f"[green]File saved under {filepath}\\result.html[/green]")
    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(htmlcontent, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)
    try:
        console.print(f"[cyan]Sending email to {config['to']}[/cyan]")
        # Send the message via local SMTP server.
        s = smtplib.SMTP(config['smtp'], config['smtp_port'])
        # sendmail function takes 3 arguments: sender's address, recipient's address
        # and message to send - here it is sent as one string.
        s.sendmail(config['from'], config['to'], msg.as_string())
        s.quit()
    except SMTPException as e:
        console.print(f"[red]Error sending email: {str(e)}[/red]")


def initEmailConfig():

    config = {
        'smtp': 'yourserver',
        'smtp_port': 25,
        'from': 'from@server.com',
        'to': 'to@server.com'
    }
    userPath = expanduser('~')
    saveFilePath = r'%s\Documents\.gitcheck' % userPath
    if not os.path.exists(saveFilePath):
        os.makedirs(saveFilePath)
    filename = saveFilePath + '\mail.properties'
    with open(filename, 'w') as fp:
        json.dump(config, fp=fp, indent=4)
    console.print(f'[yellow]Please, modify config file located here: {filename}[/yellow]')


def readDefaultConfig():
    filename = expanduser('~/.gitcheck')
    if os.path.exists(filename):
        pass


def usage():
    console.print(f"[bold cyan]Usage:[/bold cyan] {sys.argv[0]} [OPTIONS]")
    console.print("[bold]Check multiple git repository in one pass[/bold]\n")
    console.print("[bold yellow]== Common options ==[/bold yellow]")
    console.print("  [green]-v, --verbose[/green]                        Show files & commits")
    console.print("  [green]--debug[/green]                              Show debug message")
    console.print("  [green]-r, --remote[/green]                         force remote update (slow)")
    console.print("  [green]-u, --untracked[/green]                      Show untracked files")
    console.print("  [green]-b, --bell[/green]                           bell on action needed")
    console.print("  [green]-w <sec>, --watch=<sec>[/green]              after displaying, wait <sec> and run again")
    console.print("  [green]-i <re>, --ignore-branch=<re>[/green]        ignore branches matching the regex <re>")
    console.print("  [green]-d <dir>, --dir=<dir>[/green]                Search <dir> for repositories (can be used multiple times)")
    console.print("  [green]-m <maxdepth>, --maxdepth=<maxdepth>[/green] Limit the depth of repositories search")
    console.print("  [green]-q, --quiet[/green]                          Display info only when repository needs action")
    console.print("  [green]-e, --email[/green]                          Send an email with result as html, using mail.properties parameters")
    console.print("  [green]-a, --all-branch[/green]                     Show the status of all branches")
    console.print("  [green]-l <re>, --localignore=<re>[/green]          ignore changes in local files which match the regex <re>")
    console.print("  [green]--init-email[/green]                         Initialize mail.properties file (has to be modified by user using JSON Format)")


def main():
    # Rich console handles colors automatically on all platforms
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "vhrubw:i:d:m:qeal:",
            [
                "verbose", "debug", "help", "remote", "untracked", "bell", "watch=", "ignore-branch=",
                "dir=", "maxdepth=", "quiet", "email", "init-email", "all-branch", "localignore="
            ]
        )
    except getopt.GetoptError as error:
        if error.opt == 'w' and 'requires argument' in error.msg:
            console.print("[red]Please indicate nb seconds for refresh ex: gitcheck -w10[/red]")
        else:
            console.print(f"[red]{error.msg}[/red]")
        sys.exit(2)

    readDefaultConfig()
    for opt, arg in opts:
        if opt in ["-v", "--verbose"]:
            argopts['verbose'] = True
        elif opt in ["--debug"]:
            argopts['debugmod'] = True
        elif opt in ["-r", "--remote"]:
            argopts['checkremote'] = True
        elif opt in ["-u", "--untracked"]:
            argopts['checkUntracked'] = True
        elif opt in ["-b", "--bell"]:
            argopts['bellOnActionNeeded'] = True
        elif opt in ["-w", "--watch"]:
            try:
                argopts['watchInterval'] = float(arg)
            except ValueError:
                print("option %s requires numeric value" % opt)
                sys.exit(2)
        elif opt in ["-i", "--ignore-branch"]:
            argopts['ignoreBranch'] = arg
        elif opt in ["-l", "--localignore"]:
            argopts['ignoreLocal'] = arg
        elif opt in ["-d", "--dir"]:
            dirs = argopts.get('searchDir', [])
            if (dirs == []):
                argopts['searchDir'] = dirs
            dirs.append(arg)
        elif opt in ["-m", '--maxdepth']:
            try:
                argopts['depth'] = int(arg)
            except ValueError:
                console.print(f"[red]option {opt} requires int value[/red]")
                sys.exit(2)
        elif opt in ["-q", "--quiet"]:
            argopts['quiet'] = True
        elif opt in ["-e", "--email"]:
            argopts['email'] = True
        elif opt in ["-a", "--all-branch"]:
            argopts['checkall'] = True
        elif opt in ["--init-email"]:
            initEmailConfig()
            sys.exit(0)
        elif opt in ["-h", "--help"]:
            usage()
            sys.exit(0)
#        else:
#            print "Unhandled option %s" % opt
#            sys.exit(2)

    while True:
        try:
            gitcheck()

            if argopts.get('email', False):
                sendReport(html.msg)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            console.print(f"[red]Unexpected error: {str(e)}[/red]")

        if argopts.get('watchInterval', 0) > 0:
            time.sleep(argopts.get('watchInterval', 0))
        else:
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
