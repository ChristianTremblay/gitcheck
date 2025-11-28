.. image:: https://travis-ci.org/badele/gitcheck.svg?branch=unittest
    :target: https://travis-ci.org/badele/gitcheck


gitcheck
========

**Modernized for Python 3 with Rich terminal output!**

When working simultaneously on several git repositories, it is easy to
lose the overview on the advancement of your work. This is why gitcheck
was created - a tool which reports the status of the repositories it
finds in a file tree. This report can be displayed on the terminal with
beautiful, colorful output using the Rich library, or sent by email.

Now you can also check your host git from a docker container. See the docker section


Requirements
------------

- Python 3.8 or higher
- Git


Installation
------------

Using pip:

::

    pip install git+git://github.com/badele/gitcheck.git

Using pipx (recommended for CLI tools):

::

    pipx install git+https://github.com/badele/gitcheck.git

Using uv:

::

    uv tool install git+https://github.com/badele/gitcheck.git

Or for development:

::

    git clone https://github.com/badele/gitcheck.git
    cd gitcheck
    pip install -e .

With uv for development:

::

    git clone https://github.com/badele/gitcheck.git
    cd gitcheck
    uv venv
    uv pip install -e .

The project uses modern ``pyproject.toml`` for configuration.


Examples
--------

Simple report
~~~~~~~~~~~~~

In a simple invocation, gitcheck shows for each repository found in
the file tree rooted at the current working directory if they have
changes to be committed or commits to be pushed.

.. code:: bash

    $ gitcheck.py

.. figure:: http://bruno.adele.im/static/gitcheck.png
   :alt: Gitcheck simple report

   Gitcheck simple report

Detailed report
~~~~~~~~~~~~~~~

This invocation is substantially identical to the previous one, but
the generated report also enumerates modified files and pending
commits.

.. code:: bash

    $ gitcheck.py -v

.. figure:: http://bruno.adele.im/static/gitcheck_verbose_v2.png
   :alt: Gitcheck detailed report

   Gitcheck detailed report

Interactive mode
~~~~~~~~~~~~~~~~

Interactive mode helps you batch-process all repositories with uncommitted changes.
It will pull latest changes, then for each repository with local modifications:

- Show the changed files
- Open TortoiseGit (if installed) to review changes
- Prompt you to commit, discard, or skip
- Optionally push commits to remote

.. code:: bash

    $ gitcheck.py -I
    # or combine with quiet mode to only process repos needing action
    $ gitcheck.py -qI

**Note:** Requires TortoiseGit to be installed for the visual diff feature.
You can also commit via command line within the interactive mode.

Auto-pull and parallel processing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Speed up repository updates with parallel processing and automatic safe pulls:

.. code:: bash

    # Update remotes in parallel (4 workers by default)
    $ gitcheck.py -r -j
    
    # Use 8 parallel workers
    $ gitcheck.py -r -j --jobs=8
    
    # Auto-pull safe repositories (no conflicts, no uncommitted changes)
    $ gitcheck.py -p
    
    # Combine parallel + auto-pull for maximum speed
    $ gitcheck.py -p -j --jobs=8

**Parallel mode benefits:**
- 4x-8x faster for multiple repositories
- Progress bar shows real-time status
- Thread-safe output
- Perfect for automation (TactRMM, cron jobs)

**Auto-pull safety:**
- Only pulls if no uncommitted changes
- Uses ``--ff-only`` (fast-forward only, no merge commits)
- Skips repos with local commits not yet pushed
- Shows exactly which repos were pulled vs skipped

Gitcheck customization
~~~~~~~~~~~~~~~~~~~~~~

You can customize the output color, the gitcheck try to find `~/mygitcheck.py`
if it found, it is imported, see the `mygitcheck.py.sample`


Docker container
~~~~~~~~~~~~~~~

You can check your git repositories from an docker container (from your host)

From the host, you can use this command

.. code:: bash

    $ docker run --rm -v `pwd`:/files:ro badele/alpine-gitcheck

or

.. code:: bash

    $ docker run --rm -v `pwd`:/files:ro badele/alpine-gitcheck cd /files && gitcheck OPTIONS

You can also create a shell function into the host, exemple for ZSH

.. code:: bash

    gitcheck (){
        docker run --rm -v `pwd`:/files:ro badele/alpine-gitcheck
    }
    #
    $ gitcheck

More info about the gitcheck container https://registry.hub.docker.com/u/badele/alpine-gitcheck/


Options
~~~~~~~

.. code:: plaintext

    -v, --verbose                        Show files & commits
    --debug                              Show debug message
    -r, --remote                         force remote update(slow)
    -u, --untracked                      Show untracked files
    -b, --bell                           bell on action needed
    -w <sec>, --watch=<sec>              after displaying, wait <sec> and run again
    -i <re>, --ignore-branch=<re>        ignore branches matching the regex <re>
    -d <dir>, --dir=<dir>                Search <dir> for repositories
    -m <maxdepth>, --maxdepth=<maxdepth> Limit the depth of repositories search
    -q, --quiet                          Display info only when repository needs action
    -e, --email                          Send an email with result as html, using mail.properties parameters
    --init-email                         Initialize mail.properties file (has to be modified by user using JSON Format)

Email Configuration
~~~~~~~~~~~~~~~~~~~

To send email reports, first initialize the configuration:

.. code:: bash

    $ gitcheck --init-email

This creates a ``mail.properties`` file in ``~/.gitcheck/`` directory.

Edit the file with your SMTP settings:

.. code:: json

    {
        "smtp": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "your_email@gmail.com",
        "use_tls": true,
        "use_ssl": false,
        "from": "your_email@gmail.com",
        "to": "recipient@example.com"
    }

**Configuration options:**

- ``smtp``: SMTP server hostname
- ``smtp_port``: Port number (587 for TLS, 465 for SSL, 25 for unencrypted)
- ``smtp_username``: Username for authentication (usually your email)
- ``use_tls``: Use STARTTLS encryption (recommended for port 587)
- ``use_ssl``: Use implicit SSL encryption (recommended for port 465)
- ``from``: Sender email address
- ``to``: Recipient email address

**Note:** Set either ``use_tls`` OR ``use_ssl`` to true, not both.

For SMTP authentication, set the password via environment variable:

.. code:: bash

    # Linux/Mac
    export GITCHECK_SMTP_PASSWORD="your_password"
    
    # Windows PowerShell
    $env:GITCHECK_SMTP_PASSWORD="your_password"
    
    # Then run gitcheck with email option
    gitcheck -e

**Note:** The password is read from the ``GITCHECK_SMTP_PASSWORD`` environment variable for security (not stored in the config file).

SSH Key Configuration
~~~~~~~~~~~~~~~~~~~~~

If your Git repositories require SSH authentication and you have multiple SSH keys or need to specify a particular key, you can configure it in several ways:

**For Pageant (PuTTY) users on Windows:**

If you're using Pageant with a ``.ppk`` key file (common with TortoiseGit):

.. code:: powershell

    # Make sure Pageant is running with your key loaded
    # Then set the key path (even though it's already in Pageant)
    $env:GITCHECK_SSH_KEY="C:\Users\YourName\.ssh\yourkey.ppk"
    gitcheck -r

Or use the command-line argument:

.. code:: powershell

    gitcheck -r --ssh-key="C:\Users\ctremblay\.ssh\ctremblay.ppk"

**Note:** Gitcheck will automatically detect the ``.ppk`` extension and use TortoiseGitPlink or plink.exe to connect through Pageant.

**For OpenSSH users (Linux/Mac/Windows):**

**Option 1: Command-line argument**

.. code:: bash

    gitcheck -r --ssh-key=/path/to/your/private_key

**Option 2: Environment variable** (recommended for regular use)

.. code:: bash

    # Linux/Mac
    export GITCHECK_SSH_KEY="$HOME/.ssh/id_rsa_work"
    gitcheck -r
    
    # Windows PowerShell
    $env:GITCHECK_SSH_KEY="C:\Users\YourName\.ssh\id_rsa_work"
    gitcheck -r

**Option 3: SSH Config** (best for permanent setup)

Edit ``~/.ssh/config`` (or ``C:\Users\YourName\.ssh\config`` on Windows):

.. code:: text

    Host git.servisys.com
        HostName git.servisys.com
        User git
        IdentityFile ~/.ssh/id_rsa_work
        IdentitiesOnly yes

This way, gitcheck (and all git commands) will automatically use the correct key for that host.

French version
~~~~~~~~~~~~~~

A French version of this document is available here:
http://bruno.adele.im/projets/gitcheck/
