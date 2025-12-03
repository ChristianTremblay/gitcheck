#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GitLab Token Validator

Validates GitLab/GitHub personal access tokens before running gitcheck.
Can be used standalone for TactRMM deployment or as a pre-check.

Usage:
    python -m gitcheck.validate_token              # Interactive validation
    python -m gitcheck.validate_token --check-only # Non-interactive check (exit code only)
    python -m gitcheck.validate_token --host git.servisys.com  # Specific host
"""

import os
import sys
import argparse
import urllib.request
import urllib.error
import json

from rich.console import Console

console = Console()


def check_token_validity(token, gitlab_host="git.servisys.com"):
    """
    Validate token by making a test API call to GitLab
    
    Args:
        token: GitLab personal access token
        gitlab_host: GitLab server hostname
        
    Returns:
        tuple: (is_valid: bool, message: str, user_info: dict or None)
    """
    if not token:
        return False, "Token is empty", None
    
    # Test token by calling GitLab API /user endpoint
    url = f"https://{gitlab_host}/api/v4/user"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("PRIVATE-TOKEN", token)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                user_data = json.loads(response.read().decode('utf-8'))
                username = user_data.get('username', 'Unknown')
                name = user_data.get('name', 'Unknown')
                return True, f"Token valid for user: {name} (@{username})", user_data
            else:
                return False, f"Unexpected response code: {response.status}", None
                
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Token is invalid or expired (401 Unauthorized)", None
        elif e.code == 403:
            return False, "Token lacks required permissions (403 Forbidden)", None
        else:
            return False, f"HTTP Error {e.code}: {e.reason}", None
            
    except urllib.error.URLError as e:
        return False, f"Network error: {str(e.reason)}", None
        
    except Exception as e:
        return False, f"Validation error: {str(e)}", None


def prompt_for_token(gitlab_host="git.servisys.com"):
    """Prompt user for a new token"""
    from rich.prompt import Prompt
    
    console.print(f"\n[cyan]Get your token at: https://{gitlab_host}/-/user_settings/personal_access_tokens[/cyan]")
    console.print("[dim]Required scopes: read_api, read_repository, write_repository[/dim]")
    
    token = Prompt.ask(
        "\n[cyan]Enter your GitLab personal access token[/cyan]",
        password=False
    )
    
    return token.strip() if token else None


def save_token_permanently(token):
    """Save token to environment variable permanently"""
    import subprocess
    
    try:
        if sys.platform == 'win32':
            # Windows: Use setx command to save permanently
            subprocess.run(
                ['setx', 'GITLAB_TOKEN', token],
                capture_output=True,
                check=True
            )
            console.print("[green]✓ Token saved to Windows registry (GITLAB_TOKEN)[/green]")
            
            # Reload the token from registry into current session
            # This way the script works immediately without restarting terminal
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
                    console.print("[green]✓ Token reloaded in current session[/green]")
                else:
                    # Fallback: use the token we just tried to save
                    os.environ['GITLAB_TOKEN'] = token
            except Exception as reload_error:
                console.print(f"[yellow]Warning: Could not reload token from registry: {reload_error}[/yellow]")
                # Fallback: use the token we just tried to save
                os.environ['GITLAB_TOKEN'] = token
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
            
            console.print(f"[green]✓ Token saved to {shell_profile}[/green]")
            console.print("[yellow]Note: Run 'source {shell_profile}' or restart terminal[/yellow]")
            
            # Update current process environment
            os.environ['GITLAB_TOKEN'] = token
        
        return True
        
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save token permanently: {str(e)}[/yellow]")
        console.print("[yellow]Token will be used for this session only[/yellow]")
        # Still update current process
        os.environ['GITLAB_TOKEN'] = token
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate GitLab personal access token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive validation with prompt
  %(prog)s --check-only             # Just check, no prompt (for scripts)
  %(prog)s --host git.example.com   # Use different GitLab instance
        """
    )
    
    parser.add_argument(
        '--host',
        default='git.servisys.com',
        help='GitLab server hostname (default: git.servisys.com)'
    )
    
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check token validity, do not prompt for new token'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Minimal output (useful for scripts)'
    )
    
    args = parser.parse_args()
    
    # Get token from environment
    token = os.environ.get('GITLAB_TOKEN', '').strip()
    
    if not token:
        if not args.quiet:
            console.print("[yellow]⚠ GITLAB_TOKEN environment variable not set[/yellow]")
        
        if args.check_only:
            if not args.quiet:
                console.print("[red]✗ No token configured[/red]")
            sys.exit(1)
        
        # Interactive mode: prompt for token
        token = prompt_for_token(args.host)
        if not token:
            console.print("[red]✗ No token provided[/red]")
            sys.exit(1)
    
    # Validate token
    if not args.quiet:
        console.print(f"\n[cyan]Validating token against {args.host}...[/cyan]")
    
    is_valid, message, user_info = check_token_validity(token, args.host)
    
    if is_valid:
        if not args.quiet:
            console.print(f"[green]✓ {message}[/green]")
        
        # If token was just entered, save it
        if not os.environ.get('GITLAB_TOKEN'):
            if not args.quiet:
                console.print("\n[cyan]Saving token...[/cyan]")
            save_token_permanently(token)
        
        sys.exit(0)
    else:
        if not args.quiet:
            console.print(f"[red]✗ Token validation failed: {message}[/red]")
        
        if args.check_only:
            sys.exit(1)
        
        # Interactive mode: allow retry
        console.print("\n[yellow]Would you like to enter a new token?[/yellow]")
        new_token = prompt_for_token(args.host)
        
        if not new_token:
            console.print("[red]✗ No token provided[/red]")
            sys.exit(1)
        
        # Validate new token
        is_valid, message, user_info = check_token_validity(new_token, args.host)
        
        if is_valid:
            console.print(f"[green]✓ {message}[/green]")
            console.print("\n[cyan]Saving token...[/cyan]")
            save_token_permanently(new_token)
            sys.exit(0)
        else:
            console.print(f"[red]✗ New token is also invalid: {message}[/red]")
            sys.exit(1)


if __name__ == "__main__":
    main()
