"""gCTS methods"""

import sap.cli.core
import sap.cli.helpers
import sap.rest.gcts


def print_gcts_message(console, log, prefix=' '):
    """Print out the message with its protocol if it exists."""

    if isinstance(log, str):
        message = log
    else:
        message = log.get('message', None)

    if message:
        console.printerr(prefix, message)
        prefix = prefix + '  '

    if not isinstance(log, dict):
        return

    try:
        protocol = log['protocol']
    except KeyError:
        return

    if isinstance(protocol, dict):
        protocol = [protocol]

    for protocol_item in protocol:
        print_gcts_message(console, protocol_item, prefix=prefix)


def dump_gcts_messages(console, messages):
    """Dumps gCTS exception to console"""

    output = False
    errlog = messages.get('errorLog', None)
    if errlog:
        output = True
        console.printerr('Error Log:')
        for errmsg in errlog:
            print_gcts_message(console, errmsg)

    msglog = messages.get('log', None)
    if msglog:
        output = True
        console.printerr('Log:')
        for logmsg in msglog:
            print_gcts_message(console, logmsg)

    exception = messages.get('exception', None)
    if exception:
        output = True
        console.printerr('Exception:\n ', messages['exception'])

    if not output:
        console.printerr(str(messages))


def print_gcts_commit(console, commit_data):
    """Prints out gCTS commit description"""

    console.printout('commit', commit_data['id'])
    console.printout('Author:', commit_data['author'], f'<{commit_data["authorMail"]}>')
    console.printout('Date:  ', commit_data['date'])
    console.printout('\n   ', commit_data['message'])


class UserCommandGroup(sap.cli.core.CommandGroup):
    """Container for user commands."""

    def __init__(self):
        super().__init__('user')


@UserCommandGroup.argument('-t', '--token')
@UserCommandGroup.argument('-a', '--api-url')
@UserCommandGroup.command('set-credentials')
def user_credentials(connection, args):
    """Set user credentials"""

    sap.rest.gcts.simple_set_user_api_token(connection, args.api_url, args.token)


class RepoCommandGroup(sap.cli.core.CommandGroup):
    """Container for repository commands."""

    def __init__(self):
        super().__init__('repo')


@RepoCommandGroup.argument('url')
@RepoCommandGroup.argument('package')
@RepoCommandGroup.command('set-url')
def set_url(connection, args):
    """Set repo URL"""

    repo = sap.rest.gcts.Repository(connection, args.package)
    sap.cli.core.printout(repo.set_url(args.url))


class CommandGroup(sap.cli.core.CommandGroup):
    """Adapter converting command line parameters to sap.rest.gcts
       methods calls.
    """

    def __init__(self):
        super().__init__('gcts')

        self.user_grp = UserCommandGroup()
        self.repo_grp = RepoCommandGroup()

    def install_parser(self, arg_parser):
        gcts_group = super().install_parser(arg_parser)

        user_parser = gcts_group.add_parser(self.user_grp.name)
        self.user_grp.install_parser(user_parser)

        repo_parser = gcts_group.add_parser(self.repo_grp.name)
        self.repo_grp.install_parser(repo_parser)


class TableWriter:
    """A helper class for formatting a list of objects into a table"""

    def __init__(self, data, attrs, headers):
        self._headers = headers
        self._widths = [len(h) for h in headers]
        self._lines = []

        for item in data:
            line = []

            for i, attr in enumerate(attrs):
                val = str(getattr(item, attr))

                if self._widths[i] < len(val):
                    self._widths[i] = len(val)

                line.append(val)

            self._lines.append(line)

    def printout(self, console, separator=" | "):
        """Prints out the content"""

        fmt = separator.join(('{:<%s}' % (w) for w in self._widths))

        console.printout(fmt.format(*self._headers))
        console.printout('-' * (sum(self._widths) + len(separator) * (len(self._headers) - 1)))

        for line in self._lines:
            console.printout(fmt.format(*line))


@CommandGroup.command()
# pylint: disable=unused-argument
def repolist(connection, args):
    """ls"""

    console = sap.cli.core.get_console()

    try:
        response = sap.rest.gcts.simple_fetch_repos(connection)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(console, ex.messages)
        return 1

    columns = ('name', 'branch', 'head', 'status', 'vsid', 'url')
    headers = ('Name', 'Branch', 'Commit', 'Status', 'vSID', 'URL')

    TableWriter(response, columns, headers).printout(console)

    return 0


@CommandGroup.argument('--heartbeat', type=int, nargs='?', default=0)
@CommandGroup.argument('--vsid', type=str, nargs='?', default='6IT')
@CommandGroup.argument('--starting-folder', type=str, nargs='?', default='src/')
@CommandGroup.argument('--no-fail-exists', default=False, action='store_true')
@CommandGroup.argument('--vcs-token', type=str, nargs='?')
@CommandGroup.argument('-t', '--type', choices=['GITHUB', 'GIT'], default='GITHUB')
@CommandGroup.argument('-r', '--role', choices=['SOURCE', 'TARGET'], default='SOURCE',
                       help='SOURCE=Development, TARGET=Provided')
@CommandGroup.argument('package', nargs='?')
@CommandGroup.argument('url')
@CommandGroup.command()
def clone(connection, args):
    """git clone <repository> [<package>]
    """

    package = args.package
    if not package:
        package = sap.rest.gcts.package_name_from_url(args.url)

    console = sap.cli.core.get_console()

    try:
        with sap.cli.helpers.ConsoleHeartBeat(console, args.heartbeat):
            repo = sap.rest.gcts.simple_clone(connection, args.url, package,
                                              start_dir=args.starting_folder,
                                              vcs_token=args.vcs_token,
                                              vsid=args.vsid,
                                              error_exists=not args.no_fail_exists,
                                              role=args.role,
                                              typ=args.type)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
        return 1

    console.printout('Cloned repository:')
    console.printout(' URL   :', repo.url)
    console.printout(' branch:', repo.branch)
    console.printout(' HEAD  :', repo.head)

    return 0


@CommandGroup.argument('package')
@CommandGroup.argument('-l', '--list', default=False, action='store_true')
@CommandGroup.command()
def config(connection, args):
    """git config [-l] [<package>]
    """

    console = sap.cli.core.get_console()

    if args.list:
        repo = sap.rest.gcts.Repository(connection, args.package)

        try:
            configuration = repo.configuration
        except sap.rest.gcts.GCTSRequestError as ex:
            dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
            return 1

        for key, value in configuration.items():
            console.printout(f'{key}={value}')

        return 0

    console.printerr('Invalid command line options\nRun: sapcli gcts config --help')
    return 1


@CommandGroup.argument('package')
@CommandGroup.command()
def delete(connection, args):
    """rm
    """

    try:
        sap.rest.gcts.simple_delete(connection, args.package)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
        return 1

    sap.cli.core.printout(f'The repository "{args.package}" has been deleted')
    return 0


@CommandGroup.argument('--heartbeat', type=int, nargs='?', default=0)
@CommandGroup.argument('branch')
@CommandGroup.argument('package')
@CommandGroup.command()
def checkout(connection, args):
    """git checkout <branch>
    """

    repo = sap.rest.gcts.Repository(connection, args.package)
    old_branch = repo.branch

    console = sap.cli.core.get_console()

    try:
        with sap.cli.helpers.ConsoleHeartBeat(console, args.heartbeat):
            response = sap.rest.gcts.simple_checkout(connection, args.branch, repo=repo)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
        return 1

    console.printout(f'The repository "{args.package}" has been set to the branch "{args.branch}"')
    console.printout(f'({old_branch}:{response["fromCommit"]}) -> ({args.branch}:{response["toCommit"]})')
    return 0


@CommandGroup.argument('package')
@CommandGroup.command('log')
def gcts_log(connection, args):
    """git log
    """

    console = sap.cli.core.get_console()
    try:
        commits = sap.rest.gcts.simple_log(connection, name=args.package)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(console, ex.messages)
        return 1

    if not commits:
        return 0

    commit_iter = iter(commits)

    commit_item = next(commit_iter)
    print_gcts_commit(console, commit_item)

    for commit_item in commit_iter:
        console.printout('')
        print_gcts_commit(console, commit_item)

    return 0


@CommandGroup.argument('--heartbeat', type=int, nargs='?', default=0)
@CommandGroup.argument('package')
@CommandGroup.command()
def pull(connection, args):
    """git pull
    """

    console = sap.cli.core.get_console()

    try:
        with sap.cli.helpers.ConsoleHeartBeat(console, args.heartbeat):
            response = sap.rest.gcts.simple_pull(connection, name=args.package)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
        return 1

    console.printout(f'The repository "{args.package}" has been pulled')
    console.printout(f'{response["fromCommit"]} -> {response["toCommit"]}')
    return 0


@CommandGroup.argument('--heartbeat', type=int, nargs='?', default=0)
@CommandGroup.argument('--description', type=str, default=None)
@CommandGroup.argument('-m', '--message', type=str, default=None)
@CommandGroup.argument('corrnr')
@CommandGroup.argument('package')
@CommandGroup.command()
def commit(connection, args):
    """git commit
    """

    console = sap.cli.core.get_console()
    repo = sap.rest.gcts.Repository(connection, args.package)

    try:
        with sap.cli.helpers.ConsoleHeartBeat(console, args.heartbeat):
            repo.commit_transport(args.corrnr, args.message or f'Transport {args.corrnr}', args.description)
    except sap.rest.gcts.GCTSRequestError as ex:
        dump_gcts_messages(sap.cli.core.get_console(), ex.messages)
        return 1

    console.printout(f'The transport "{args.corrnr}" has been committed')
    return 0
