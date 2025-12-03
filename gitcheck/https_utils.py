#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HTTPS/OAuth token management utilities for gitcheck

This module handles:
- Converting git://, SSH URLs to HTTPS
- OAuth token injection for GitLab/GitHub
- Interactive token prompting
- Persistent token storage
- Token expiration detection and retry logic
"""

import os
import sys
import re
import subprocess

from rich.prompt import Prompt


def promptForToken(console, console_lock):
    """
    Prompt user for GitLab/GitHub personal access token
    
    Args:
        console: Rich Console instance
        console_lock: Threading lock for console output
        
    Returns:
        str: Token entered by user, or None if skipped
    """
    with console_lock:
        console.print("\n[yellow]⚠ GITLAB_TOKEN environment variable not set[/yellow]")
        console.print("[yellow]For GitLab/private repos, you need a personal access token[/yellow]")
        console.print("[cyan]Get your token at: https://git.servisys.com/-/user_settings/personal_access_tokens[/cyan]")
        console.print("[dim]Required scopes: read_repository, write_repository (for pull operations)[/dim]")
        
        token_input = Prompt.ask(
            "\n[cyan]Enter your GitLab/Git personal access token (or press Enter to skip)[/cyan]",
            password=True,
            default=""
        )
        
        if token_input.strip():
            return token_input.strip()
        else:
            console.print("[yellow]Skipping OAuth token injection for this session...\n[/yellow]")
            return None


def promptForNewToken(console, console_lock, reason="expired or invalid"):
    """
    Prompt user for a new token when the current one is expired/invalid
    
    Args:
        console: Rich Console instance
        console_lock: Threading lock for console output
        reason: Reason why new token is needed
        
    Returns:
        str: New token entered by user, or None if skipped
    """
    with console_lock:
        console.print(f"\n[yellow]⚠ GitLab token appears to be {reason}[/yellow]")
        console.print("[yellow]Authentication failed. Please provide a new token.[/yellow]")
        console.print("[cyan]Get your token at: https://git.servisys.com/-/user_settings/personal_access_tokens[/cyan]")
        console.print("[dim]Required scopes: read_repository, write_repository (for pull operations)[/dim]")
        
        token_input = Prompt.ask(
            "\n[cyan]Enter your new GitLab/Git personal access token (or press Enter to skip)[/cyan]",
            password=False,
            default=""
        )
        
        if token_input.strip():
            return token_input.strip()
        else:
            console.print("[yellow]No token provided. Skipping...[/yellow]\n")
            return None


def saveTokenPermanently(token, console, console_lock):
    """
    Save token to environment variable permanently
    
    Args:
        token: Token to save
        console: Rich Console instance
        console_lock: Threading lock for console output
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        if sys.platform == 'win32':
            # Windows: Use setx command to save permanently
            subprocess.run(
                ['setx', 'GITLAB_TOKEN', token],
                capture_output=True,
                check=True
            )
            with console_lock:
                console.print("[green]✓ Token saved to Windows registry (GITLAB_TOKEN)[/green]")
            
            # Reload the token from registry into current session
            # This way gitcheck works immediately without restarting terminal
            try:
                result = subprocess.run(
                    ['powershell', '-Command', 
                     "[System.Environment]::GetEnvironmentVariable('GITLAB_TOKEN', 'User')"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                reloaded_token = result.stdout.strip()
                if reloaded_token:
                    os.environ['GITLAB_TOKEN'] = reloaded_token
                    with console_lock:
                        console.print("[green]✓ Token reloaded in current session[/green]")
                else:
                    # Fallback: use the token we just tried to save
                    os.environ['GITLAB_TOKEN'] = token
            except Exception as reload_error:
                with console_lock:
                    console.print(f"[yellow]Warning: Could not reload token from registry: {reload_error}[/yellow]")
                # Fallback: use the token we just tried to save
                os.environ['GITLAB_TOKEN'] = token
                with console_lock:
                    console.print("[yellow]Note: Token saved but you may need to restart terminal[/yellow]")
        else:
            # Unix-like: Append to shell profile
            shell_profile = os.path.expanduser('~/.bashrc')
            if os.path.exists(os.path.expanduser('~/.zshrc')):
                shell_profile = os.path.expanduser('~/.zshrc')
            
            # Read existing file and remove old token line
            with open(shell_profile, 'r') as f:
                lines = f.readlines()
            
            with open(shell_profile, 'w') as f:
                for line in lines:
                    if 'GITLAB_TOKEN' not in line:
                        f.write(line)
                f.write(f'\nexport GITLAB_TOKEN="{token}"\n')
            
            with console_lock:
                console.print(f"[green]✓ Token saved to {shell_profile}[/green]")
                console.print("[yellow]Note: Run 'source {shell_profile}' or restart terminal[/yellow]")
            
            # Update current process environment
            os.environ['GITLAB_TOKEN'] = token
        
        return True
    except Exception as e:
        with console_lock:
            console.print(f"[yellow]Warning: Could not save token permanently: {str(e)}[/yellow]")
            console.print("[yellow]Token will be used for this session only[/yellow]")
        # Still update current process
        os.environ['GITLAB_TOKEN'] = token
        return False


def convertRemoteToHttps(rep, remote_name, gitlab_token, git_exec_func, force_update=False):
    """
    Convert git:// or SSH remote URLs to HTTPS for firewall compatibility
    
    Args:
        rep: Repository path
        remote_name: Name of the remote (e.g., 'origin')
        gitlab_token: OAuth token for authentication (can be None)
        git_exec_func: Function to execute git commands
        force_update: If True, update URL even if already HTTPS with token (for new token)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Get current remote URL
        result = git_exec_func(rep, f"remote get-url {remote_name}")
        current_url = result.strip()
        
        if not current_url:
            return False, "No remote URL found"
        
        # Strip old token from URL to get clean URL for re-conversion
        clean_url = current_url
        if 'oauth2:' in current_url:
            # Remove old token: https://oauth2:OLD_TOKEN@host/path -> https://host/path
            clean_url = re.sub(r'https://oauth2:[^@]+@', 'https://', current_url)
        
        # Check if already HTTPS with current token (and not forcing update)
        if not force_update and current_url.startswith('https://') and gitlab_token and f'oauth2:{gitlab_token}@' in current_url:
            return False, "Already using HTTPS with current token"
        
        new_url = None
        
        # Convert git:// to https://
        if clean_url.startswith('git://'):
            new_url = clean_url.replace('git://', 'https://')
        
        # Convert SSH URLs (git@host:path) to HTTPS
        elif clean_url.startswith('git@'):
            # Pattern: git@github.com:user/repo.git -> https://github.com/user/repo.git
            match = re.match(r'git@([^:]+):(.+)', clean_url)
            if match:
                host = match.group(1)
                path = match.group(2)
                new_url = f'https://{host}/{path}'
        
        # Convert ssh:// URLs
        elif clean_url.startswith('ssh://'):
            # Pattern: ssh://git@github.com/user/repo.git -> https://github.com/user/repo.git
            new_url = clean_url.replace('ssh://git@', 'https://')
            new_url = new_url.replace('ssh://', 'https://')
        
        # If already HTTPS (use clean URL without old token), inject new token if available
        elif clean_url.startswith('https://') and gitlab_token:
            # Pattern: https://host/path -> https://oauth2:token@host/path
            match = re.match(r'https://(.+)', clean_url)
            if match:
                new_url = f'https://oauth2:{gitlab_token}@{match.group(1)}'
        
        if new_url:
            # Inject OAuth token if available and not already present
            if gitlab_token and 'oauth2:' not in new_url:
                # Pattern: https://host/path -> https://oauth2:token@host/path
                match = re.match(r'https://(.+)', new_url)
                if match:
                    new_url = f'https://oauth2:{gitlab_token}@{match.group(1)}'
            
            # Update the remote URL
            git_exec_func(rep, f"remote set-url {remote_name} {new_url}")
            
            # Sanitize token in display message
            display_url = new_url
            if gitlab_token:
                display_url = new_url.replace(gitlab_token, '***TOKEN***')
            
            return True, f"Converted {current_url} -> {display_url}"
        else:
            return False, "URL format not recognized for conversion"
            
    except Exception as e:
        return False, f"Error: {str(e)}"


def ensureHttpsRemotes(rep, get_remotes_func, convert_func, verbose=False, console=None, console_lock=None, force_update=False):
    """
    Ensure all remotes use HTTPS URLs
    
    Args:
        rep: Repository path
        get_remotes_func: Function to get list of remotes
        convert_func: Function to convert a single remote
        verbose: Whether to print verbose output
        console: Rich Console instance (required if verbose=True)
        console_lock: Threading lock (required if verbose=True)
        force_update: If True, update URLs even if already HTTPS (for new token)
        
    Returns:
        tuple: (converted: bool, info: list of tuples)
    """
    try:
        remotes = get_remotes_func(rep)
        converted = []
        
        for remote in remotes:
            success, message = convert_func(rep, remote, force_update=force_update)
            if success:
                converted.append((remote, message))
                if verbose and console and console_lock:
                    with console_lock:
                        console.print(f"  [cyan]→ {remote}: {message}[/cyan]")
        
        return len(converted) > 0, converted
    except Exception as e:
        return False, str(e)


def isAuthenticationError(error_message):
    """
    Check if error message indicates authentication failure
    
    Args:
        error_message: Error message string
        
    Returns:
        bool: True if authentication error detected
    """
    error_msg = error_message.lower()
    
    auth_indicators = [
        'authentication failed',
        'invalid credentials',
        'token expired',
        'unauthorized',
        'http basic: access denied',
        'ssl certificate problem',
        'certificate verify failed',
        'could not read username',
        'could not read password',
        '401',
        '403'
    ]
    
    return any(indicator in error_msg for indicator in auth_indicators)
