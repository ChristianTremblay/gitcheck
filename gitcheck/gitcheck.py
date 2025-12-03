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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from . import https_utils

console = Console()
console_lock = threading.Lock()

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


def convertRemoteToHttps(rep, remote_name='origin', force_update=False):
    """Convert git:// or SSH remote URLs to HTTPS for firewall compatibility"""
    gitlab_token = os.environ.get('GITLAB_TOKEN', '').strip()
    return https_utils.convertRemoteToHttps(rep, remote_name, gitlab_token, gitExec, force_update=force_update)


def promptForNewToken(reason="expired or invalid"):
    """Prompt user for a new token and save it"""
    new_token = https_utils.promptForNewToken(console, console_lock, reason)
    if new_token:
        # Save to environment for current process
        os.environ['GITLAB_TOKEN'] = new_token
        # Save permanently
        https_utils.saveTokenPermanently(new_token, console, console_lock)
    return new_token


def ensureHttpsRemotes(rep, force_update=False):
    """Ensure all remotes use HTTPS URLs"""
    return https_utils.ensureHttpsRemotes(
        rep,
        getRemoteRepositories,
        convertRemoteToHttps,
        verbose=argopts.get('verbose', False),
        console=console,
        console_lock=console_lock,
        force_update=force_update
    )


def updateRemote(rep):
    try:
        # Convert to HTTPS if requested (for firewall bypass)
        if argopts.get('use_https', False):
            converted, info = ensureHttpsRemotes(rep)
            if converted and not argopts.get('verbose', False):
                with console_lock:
                    console.print(f"  [dim]Converted {len(info)} remote(s) to HTTPS[/dim]")
        
        # Use verbose mode to show what's being updated
        # Set a timeout to prevent hanging on slow/unresponsive remotes
        result = gitExec(rep, "remote update", timeout=30)
        if argopts.get('verbose', False) and result.strip():
            # Show the output from remote update
            for line in result.split('\n'):
                if line.strip():
                    console.print(f"  [dim]{line}[/dim]")
    except subprocess.TimeoutExpired:
        raise Exception("Network timeout - remote server not responding")
    except Exception as e:
        # Check for authentication failures that indicate expired/invalid token
        if https_utils.isAuthenticationError(str(e)):
            # Token appears to be expired or invalid
            if argopts.get('use_https', False):
                # Only prompt once per session
                if not hasattr(updateRemote, '_token_retry_attempted'):
                    updateRemote._token_retry_attempted = True
                    
                    new_token = promptForNewToken()
                    if new_token:
                        # Retry with new token - re-convert remotes with force_update=True
                        converted, info = ensureHttpsRemotes(rep, force_update=True)
                        # Retry the update
                        result = gitExec(rep, "remote update", timeout=30)
                        if argopts.get('verbose', False) and result.strip():
                            for line in result.split('\n'):
                                if line.strip():
                                    console.print(f"  [dim]{line}[/dim]")
                        return
        
        raise e


def canSafelyPull(rep, branch):
    """Check if repository can be safely pulled without conflicts"""
    # Check if there are uncommitted changes
    changes = getLocalFilesChange(rep)
    if len(changes) > 0:
        return False, "Has uncommitted changes"
    
    # Check if branch has remote
    remotes = getRemoteRepositories(rep)
    if not remotes:
        return False, "No remote configured"
    
    # For each remote, check if we can fast-forward
    for remote in remotes:
        if not hasRemoteBranch(rep, remote, branch):
            continue
        
        # Check if pull would be a fast-forward (no merge needed)
        try:
            # Check if local branch is behind remote
            behind = getRemoteToPull(rep, remote, branch)
            if not behind:
                continue  # Already up to date
            
            # Check if local branch has commits not on remote
            ahead = getLocalToPush(rep, remote, branch)
            if ahead:
                return False, f"Branch has local commits not pushed to {remote}"
            
            # Safe to pull - we're only behind, not ahead
            return True, f"Can fast-forward from {remote}"
        except Exception as e:
            return False, f"Error checking {remote}: {str(e)}"
    
    return False, "No remote branches to pull from"


def autoPullRepository(rep, branch):
    """Attempt to safely pull repository if possible"""
    can_pull, reason = canSafelyPull(rep, branch)
    
    if not can_pull:
        showDebug(f"Skipping auto-pull for {rep}: {reason}")
        return False
    
    try:
        with console_lock:
            console.print(f"  [cyan]→ Auto-pulling {branch}...[/cyan]")
        
        result = gitExec(rep, "pull --ff-only")
        
        if argopts.get('verbose', False) and result.strip():
            with console_lock:
                for line in result.split('\n'):
                    if line.strip():
                        console.print(f"    [dim]{line}[/dim]")
        
        with console_lock:
            console.print("  [green]✓ Pulled successfully[/green]")
        return True
    except Exception as e:
        # Check for authentication failures
        if https_utils.isAuthenticationError(str(e)):
            if argopts.get('use_https', False):
                if not hasattr(autoPullRepository, '_token_retry_attempted'):
                    autoPullRepository._token_retry_attempted = True
                    
                    new_token = promptForNewToken()
                    if new_token:
                        # Re-convert remotes with new token (force update)
                        ensureHttpsRemotes(rep, force_update=True)
                        # Retry pull
                        try:
                            result = gitExec(rep, "pull --ff-only")
                            with console_lock:
                                console.print("  [green]✓ Pulled successfully with new token[/green]")
                            return True
                        except Exception as retry_error:
                            with console_lock:
                                console.print(f"  [red]✗ Pull failed even with new token: {str(retry_error)}[/red]")
                            return False
        
        with console_lock:
            console.print(f"  [yellow]⚠ Auto-pull failed: {str(e)}[/yellow]")
        return False


def processRepository(repo_path):
    """Process a single repository (for parallel execution)"""
    result = {
        'path': repo_path,
        'success': False,
        'updated': False,
        'pulled': False,
        'error': None
    }
    
    try:
        # Update remotes
        updateRemote(repo_path)
        result['updated'] = True
        
        # Auto-pull if enabled
        if argopts.get('autopull', False):
            branch_set = getDefaultBranch(repo_path)
            for branch in branch_set:
                if branch:
                    if autoPullRepository(repo_path, branch):
                        result['pulled'] = True
        
        result['success'] = True
    except subprocess.TimeoutExpired:
        result['error'] = "Timeout (30s) - remote not responding"
    except Exception as e:
        result['error'] = str(e)
    
    return result


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


def gitExec(path, cmd, timeout=None):
    commandToExecute = "git -C \"%s\" %s" % (path, cmd)
    cmdargs = shlex.split(commandToExecute)
    showDebug("EXECUTE GIT COMMAND '%s'" % cmdargs)
    
    # Prepare environment with SSH key if provided
    env = os.environ.copy()
    ssh_key = argopts.get('ssh_key')
    
    # Debug: Show SSH key configuration
    env_ssh_key = os.environ.get('GITCHECK_SSH_KEY')
    if argopts.get('debugmod', False) and (env_ssh_key or ssh_key):
        console.print("[dim]SSH Key Configuration:[/dim]")
        console.print(f"[dim]  Environment variable GITCHECK_SSH_KEY: {env_ssh_key or 'Not set'}[/dim]")
        console.print(f"[dim]  argopts ssh_key: {ssh_key or 'Not set'}[/dim]")
    
    # Check if using Pageant (PuTTY) - indicated by .ppk extension
    if ssh_key and ssh_key.lower().endswith('.ppk'):
        # Use plink for PuTTY/Pageant integration
        # Find plink.exe (usually in same directory as PuTTY or TortoiseGit)
        plink_paths = [
            r"C:\Program Files\TortoiseGit\bin\TortoiseGitPlink.exe",
            r"C:\Program Files (x86)\TortoiseGit\bin\TortoiseGitPlink.exe",
            r"C:\Program Files\PuTTY\plink.exe",
            r"C:\Program Files (x86)\PuTTY\plink.exe",
        ]
        
        plink_exe = None
        for plink_path in plink_paths:
            if os.path.exists(plink_path):
                plink_exe = plink_path
                break
        
        if plink_exe:
            env['GIT_SSH'] = plink_exe
            showDebug(f"Using Pageant with plink: {plink_exe}")
            console.print(f"[dim]Using SSH via: {plink_exe}[/dim]") if argopts.get('debugmod', False) else None
        else:
            console.print("[yellow]Warning: .ppk key specified but plink.exe not found. Install TortoiseGit or PuTTY.[/yellow]")
            console.print("[yellow]Searched locations:[/yellow]")
            for path in plink_paths:
                console.print(f"[dim]  - {path}[/dim]")
    elif ssh_key and os.path.exists(ssh_key):
        # Use GIT_SSH_COMMAND for OpenSSH keys
        env['GIT_SSH_COMMAND'] = f'ssh -i "{ssh_key}" -o IdentitiesOnly=yes'
        showDebug(f"Using SSH key: {ssh_key}")
    
    p = subprocess.Popen(cmdargs, stdout=PIPE, stderr=PIPE, env=env)
    try:
        output, errors = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()  # Clean up
        raise subprocess.TimeoutExpired(cmdargs, timeout)
    
    if p.returncode:
        error_msg = errors.decode('utf-8') if errors else 'Unknown error'
        showDebug(f'Git command failed: {commandToExecute}')
        showDebug(f'Error output: {error_msg}')
        
        # Provide helpful error messages for common issues
        if 'timed out' in error_msg.lower() or 'timeout' in error_msg.lower():
            raise Exception("Network timeout - check your connection or remote server status")
        elif 'could not resolve host' in error_msg.lower():
            raise Exception("DNS resolution failed - check your network connection")
        elif 'permission denied' in error_msg.lower():
            raise Exception("Authentication failed - check SSH key or credentials")
        else:
            raise Exception(error_msg)
    return output.decode('utf-8')


# Check all git repositories
def gitcheck():
    showDebug("Global Vars: %s" % argopts)

    repo = searchRepositories()
    actionNeeded = False

    if argopts.get('checkremote', False):
        # Only prompt for token if use_https is enabled AND token is missing
        # Token will be re-prompted automatically if authentication fails during operations
        if argopts.get('use_https', False):
            gitlab_token = os.environ.get('GITLAB_TOKEN', '').strip()
            if gitlab_token == '':  # Token is missing or empty
                # Prompt for token now, before any parallel processing
                gitlab_token = https_utils.promptForToken(console, console_lock)
                if gitlab_token:
                    # Save to environment for current process
                    os.environ['GITLAB_TOKEN'] = gitlab_token
                    # Save permanently
                    https_utils.saveTokenPermanently(gitlab_token, console, console_lock)
            # else: token already exists, will be used automatically
        
        max_workers = argopts.get('jobs', 4)  # Default to 4 parallel jobs
        
        if argopts.get('parallel', False) and len(repo) > 1:
            # Parallel processing with progress bar
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    console=console
                ) as progress:
                    task = progress.add_task(f"[cyan]Processing {len(repo)} repositories...", total=len(repo))
                    
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        future_to_repo = {executor.submit(processRepository, r): r for r in repo}
                        
                        for future in as_completed(future_to_repo):
                            r = future_to_repo[future]
                            try:
                                result = future.result()
                                progress.update(task, advance=1)
                                
                                with console_lock:
                                    if result['success']:
                                        status = "✓ Updated"
                                        if result['pulled']:
                                            status += " + Pulled"
                                        console.print(f"[green]{result['path']}[/green] - {status}")
                                    else:
                                        console.print(f"[yellow]{result['path']}[/yellow] - Failed: {result['error']}")
                            except Exception as e:
                                progress.update(task, advance=1)
                                with console_lock:
                                    console.print(f"[red]{r}[/red] - Error: {str(e)}")
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠ Interrupted by user - stopping parallel processing...[/yellow]")
                raise
        else:
            # Sequential processing (original behavior)
            for r in repo:
                console.print(f"[cyan]Updating {r} remotes...[/cyan]")
                try:
                    updateRemote(r)
                    console.print("  [green]✓ Updated[/green]")
                    
                    # Auto-pull if enabled
                    if argopts.get('autopull', False):
                        # Get the current branch for this repo
                        branch_set = getDefaultBranch(r)
                        for branch in branch_set:
                            if branch:  # Skip if no branch detected
                                autoPullRepository(r, branch)
                except KeyboardInterrupt:
                    console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
                    raise
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to update remotes for {r}[/yellow]")
                    if argopts.get('debugmod', False):
                        console.print(f"[dim]Error: {str(e)}[/dim]")
                    continue

    if argopts.get('watchInterval', 0) > 0:
        console.clear()
        console.print(f"[bold]{strftime('%Y-%m-%d %H:%M:%S')}[/bold]")

    showDebug("Processing repositories... please wait.")
    for r in repo:
        try:
            if (argopts.get('checkall', False)):
                branch = getAllBranches(r)
            else:
                branch = getDefaultBranch(r)
            for b in branch:
                if checkRepository(r, b):
                    actionNeeded = True
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
            raise
    html.timestamp = strftime("%Y-%m-%d %H:%M:%S")
    html.msg += "</ul>\n<p>Report created on %s</p>\n" % html.timestamp

    if actionNeeded and argopts.get('bellOnActionNeeded', False):
        console.bell()
    
    # Interactive mode to handle uncommitted changes
    if argopts.get('interactive', False):
        handleInteractiveMode(repo)


def openTortoiseDiff(repo_path):
    """Open TortoiseGit diff tool for the repository"""
    try:
        # TortoiseGitProc.exe /command:repostatus /path:"repo_path"
        tortoise_cmd = f'TortoiseGitProc.exe /command:repostatus /path:"{repo_path}"'
        subprocess.Popen(tortoise_cmd, shell=True)
        return True
    except Exception as e:
        console.print(f"[yellow]Could not open TortoiseGit: {str(e)}[/yellow]")
        console.print("[yellow]Make sure TortoiseGit is installed and in your PATH[/yellow]")
        return False


def handleInteractiveMode(repositories):
    """Interactive mode to review and commit/discard changes"""
    console.print("\n[bold cyan]═══ Interactive Mode ═══[/bold cyan]\n")
    
    repos_with_changes = []
    for repo in repositories:
        changes = getLocalFilesChange(repo)
        if len(changes) > 0:
            repos_with_changes.append((repo, changes))
    
    if not repos_with_changes:
        console.print("[green]✓ No repositories with uncommitted changes![/green]")
        return
    
    console.print(f"[yellow]Found {len(repos_with_changes)} repository(ies) with uncommitted changes[/yellow]\n")
    
    for idx, (repo, changes) in enumerate(repos_with_changes, 1):
        console.print(f"\n[bold]Repository {idx}/{len(repos_with_changes)}:[/bold] [cyan]{repo}[/cyan]")
        console.print(f"  [yellow]{len(changes)} file(s) changed[/yellow]")
        
        # Show changed files
        for status, filename in changes[:5]:  # Show first 5
            console.print(f"    [{colortheme['commitstate']}]{status}[/] {filename}")
        if len(changes) > 5:
            console.print(f"    [dim]... and {len(changes) - 5} more[/dim]")
        
        # Ask what to do
        console.print("\n[bold]What would you like to do?[/bold]")
        console.print("  [green]1[/green] - Open TortoiseGit and commit")
        console.print("  [yellow]2[/yellow] - Skip this repository")
        console.print("  [red]3[/red] - Discard all changes (git reset --hard)")
        console.print("  [cyan]4[/cyan] - Commit via command line")
        console.print("  [magenta]q[/magenta] - Quit interactive mode")
        
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3", "4", "q"], default="2")
        
        if choice == "q":
            console.print("[yellow]Exiting interactive mode[/yellow]")
            break
        elif choice == "1":
            # Open TortoiseGit
            console.print("[cyan]Opening TortoiseGit...[/cyan]")
            if openTortoiseDiff(repo):
                if Confirm.ask("Press Enter when done with TortoiseGit commit", default=True):
                    # Check if changes still exist
                    remaining = getLocalFilesChange(repo)
                    if len(remaining) == 0:
                        console.print("[green]✓ Changes committed successfully![/green]")
                        # Ask about push
                        if Confirm.ask("  Push to remote?", default=True):
                            try:
                                gitExec(repo, "push")
                                console.print("[green]✓ Pushed to remote![/green]")
                            except Exception as e:
                                console.print(f"[red]✗ Push failed: {str(e)}[/red]")
                    else:
                        console.print(f"[yellow]Still {len(remaining)} file(s) uncommitted[/yellow]")
        elif choice == "2":
            console.print("[yellow]Skipping...[/yellow]")
            continue
        elif choice == "3":
            # Discard changes
            if Confirm.ask("[red]⚠ Are you SURE you want to discard all changes? This cannot be undone!", default=False):
                try:
                    gitExec(repo, "reset --hard")
                    console.print("[green]✓ Changes discarded[/green]")
                except Exception as e:
                    console.print(f"[red]✗ Failed to discard: {str(e)}[/red]")
            else:
                console.print("[yellow]Cancelled discard operation[/yellow]")
        elif choice == "4":
            # Command line commit
            commit_msg = Prompt.ask("Commit message")
            if commit_msg:
                try:
                    gitExec(repo, "add -A")
                    gitExec(repo, f'commit -m "{commit_msg}"')
                    console.print("[green]✓ Changes committed![/green]")
                    # Ask about push
                    if Confirm.ask("  Push to remote?", default=True):
                        try:
                            gitExec(repo, "push")
                            console.print("[green]✓ Pushed to remote![/green]")
                        except Exception as e:
                            console.print(f"[red]✗ Push failed: {str(e)}[/red]")
                except Exception as e:
                    console.print(f"[red]✗ Commit failed: {str(e)}[/red]")
            else:
                console.print("[yellow]No commit message provided, skipping[/yellow]")
    
    console.print("\n[bold cyan]═══ Interactive Mode Complete ═══[/bold cyan]\n")


def sendReport(content):
    userPath = expanduser('~')
    filepath = os.path.join(userPath, '.gitcheck')
    filename = os.path.join(filepath, 'mail.properties')
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
    with open(os.path.join(filepath, 'result.html'), 'w') as f:
        f.write(htmlcontent)
    console.print(f"[green]File saved under {os.path.join(filepath, 'result.html')}[/green]")
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
        # Send the message via SMTP server with optional authentication
        # Check if using SSL (port 465) or TLS (port 587)
        use_ssl = config.get('use_ssl', False)
        use_tls = config.get('use_tls', False)
        
        if use_ssl:
            # Use SMTP_SSL for implicit SSL (typically port 465)
            s = smtplib.SMTP_SSL(config['smtp'], config['smtp_port'], timeout=30)
            console.print("[dim]Connected using SSL...[/dim]") if argopts.get('debugmod', False) else None
        else:
            # Use regular SMTP (typically port 587 with STARTTLS or port 25)
            s = smtplib.SMTP(config['smtp'], config['smtp_port'], timeout=30)
            
            # Use TLS if configured
            if use_tls:
                console.print("[dim]Starting TLS...[/dim]") if argopts.get('debugmod', False) else None
                s.starttls()
        
        # Enable debug output if in debug mode
        if argopts.get('debugmod', False):
            s.set_debuglevel(1)
        
        # Authenticate if username is provided
        smtp_username = config.get('smtp_username')
        if smtp_username:
            # Get password from environment variable
            smtp_password = os.environ.get('GITCHECK_SMTP_PASSWORD', '')
            if not smtp_password:
                console.print("[yellow]Warning: SMTP username provided but GITCHECK_SMTP_PASSWORD environment variable not set[/yellow]")
            else:
                console.print(f"[dim]Authenticating as {smtp_username}...[/dim]") if argopts.get('debugmod', False) else None
                s.login(smtp_username, smtp_password)
        
        # sendmail function takes 3 arguments: sender's address, recipient's address
        # and message to send - here it is sent as one string.
        console.print("[dim]Sending message...[/dim]") if argopts.get('debugmod', False) else None
        s.sendmail(config['from'], config['to'], msg.as_string())
        s.quit()
        console.print("[green]Email sent successfully![/green]")
    except SMTPException as e:
        console.print(f"[red]Error sending email: {str(e)}[/red]")
        console.print("[yellow]Tip: Try running with --debug flag for more details[/yellow]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        console.print("[yellow]Check your mail.properties configuration and network connection[/yellow]")


def initEmailConfig():

    config = {
        'smtp': 'smtp.example.com',
        'smtp_port': 587,
        'smtp_username': 'your_username@example.com',
        'use_tls': True,
        'use_ssl': False,
        'from': 'from@example.com',
        'to': 'to@example.com'
    }
    userPath = expanduser('~')
    saveFilePath = os.path.join(userPath, '.gitcheck')
    if not os.path.exists(saveFilePath):
        os.makedirs(saveFilePath)
    filename = os.path.join(saveFilePath, 'mail.properties')
    with open(filename, 'w') as fp:
        json.dump(config, fp=fp, indent=4)
    console.print(f'[yellow]Please, modify config file located here: {filename}[/yellow]')
    console.print('[yellow]Note: Set GITCHECK_SMTP_PASSWORD environment variable for SMTP authentication[/yellow]')


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
    console.print("  [green]-p, --auto-pull[/green]                      Auto-pull when safe (no conflicts, no local changes)")
    console.print("  [green]-j, --parallel[/green]                       Use parallel processing for remote updates (faster)")
    console.print("  [green]--jobs=<n>[/green]                           Number of parallel jobs (default: 4)")
    console.print("  [green]--use-https[/green]                          Convert git:// and SSH URLs to HTTPS (firewall bypass)")
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
    console.print("  [green]-I, --interactive[/green]                    Interactive mode: review and commit/discard changes with TortoiseGit")
    console.print("  [green]--init-email[/green]                         Initialize mail.properties file (has to be modified by user using JSON Format)")
    console.print("  [green]--ssh-key=<path>[/green]                     Path to SSH private key for git operations")
    console.print("\n[bold yellow]== Environment Variables ==[/bold yellow]")
    console.print("  [green]GITCHECK_SMTP_PASSWORD[/green]               SMTP password for email authentication (if smtp_username is set)")
    console.print("  [green]GITCHECK_SSH_KEY[/green]                     Path to SSH private key (alternative to --ssh-key option)")
    console.print("  [green]GITLAB_TOKEN[/green]                         GitLab/private repo personal access token (for HTTPS with --use-https)")


def main():
    # Rich console handles colors automatically on all platforms
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "vhrubpjw:i:d:m:qeal:I",
            [
                "verbose", "debug", "help", "remote", "untracked", "bell", "auto-pull", "parallel", "watch=", "ignore-branch=",
                "dir=", "maxdepth=", "quiet", "email", "init-email", "all-branch", "localignore=", "interactive",
                "ssh-key=", "jobs=", "use-https"
            ]
        )
    except getopt.GetoptError as error:
        if error.opt == 'w' and 'requires argument' in error.msg:
            console.print("[red]Please indicate nb seconds for refresh ex: gitcheck -w10[/red]")
        else:
            console.print(f"[red]{error.msg}[/red]")
        sys.exit(2)

    readDefaultConfig()
    
    # Check for SSH key from environment variable
    env_ssh_key = os.environ.get('GITCHECK_SSH_KEY')
    if env_ssh_key:
        argopts['ssh_key'] = env_ssh_key
        showDebug(f"SSH key from environment: {env_ssh_key}")
    
    for opt, arg in opts:
        if opt in ["-v", "--verbose"]:
            argopts['verbose'] = True
        elif opt in ["--debug"]:
            argopts['debugmod'] = True
        elif opt in ["-r", "--remote"]:
            argopts['checkremote'] = True
        elif opt in ["-p", "--auto-pull"]:
            argopts['autopull'] = True
            # Auto-pull requires remote check
            argopts['checkremote'] = True
        elif opt in ["-j", "--parallel"]:
            argopts['parallel'] = True
        elif opt in ["--jobs"]:
            try:
                argopts['jobs'] = min(int(arg), 10)  # Limit to max 10 jobs
                if argopts['jobs'] < 1:
                    console.print("[red]Number of jobs must be at least 1[/red]")
                    sys.exit(2)
            except ValueError:
                console.print(f"[red]option {opt} requires int value[/red]")
                sys.exit(2)
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
        elif opt in ["-I", "--interactive"]:
            argopts['interactive'] = True
            # Interactive mode implies checking remotes first
            argopts['checkremote'] = True
        elif opt in ["--init-email"]:
            initEmailConfig()
            sys.exit(0)
        elif opt in ["--ssh-key"]:
            # Accept both .ppk (Pageant) and regular SSH keys
            if os.path.exists(arg) or arg.lower().endswith('.ppk'):
                argopts['ssh_key'] = arg
            else:
                console.print(f"[red]SSH key file not found: {arg}[/red]")
                sys.exit(2)
        elif opt in ["--use-https"]:
            argopts['use_https'] = True
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
