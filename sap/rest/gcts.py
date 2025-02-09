"""gCTS REST calls"""

# ABAP Package: SCTS_ABAP_AND_VCS

from sap import get_logger

from sap.errors import SAPCliError
from sap.rest.errors import HTTPRequestError


def mod_log():
    """ADT Module logger"""

    return get_logger()


class GCTSRequestError(SAPCliError):
    """Base gCTS error type"""

    def __init__(self, messages):
        super().__init__()

        self.messages = messages

    def __repr__(self):
        return f'gCTS exception: {self.messages["exception"]}'

    def __str__(self):
        return repr(self)


class GCTSRepoAlreadyExistsError(GCTSRequestError):
    """A repository already exists"""

    # pylint: disable=unnecessary-pass
    pass


class GCTSRepoNotExistsError(GCTSRequestError):
    """A repository does not exist"""

    def __init__(self, messages):
        super().__init__(messages)
        self.messages['exception'] = 'Repository does not exist'


def exception_from_http_error(http_error):
    """Converts HTTPRequestError to proper instance"""

    if 'application/json' not in http_error.response.headers.get('Content-Type', ''):
        return http_error

    messages = http_error.response.json()

    log = messages.get('log', None)
    if log and log[0].get('message', '').endswith('Error action CREATE_REPOSITORY Repository already exists'):
        return GCTSRepoAlreadyExistsError(messages)

    exception = messages.get('exception', None)
    if exception == 'No relation between system and repository':
        return GCTSRepoNotExistsError(messages)

    return GCTSRequestError(messages)


def package_name_from_url(url):
    """Parse out Package name from a repo git url"""

    url_repo_part = url.split('/')[-1]

    if url_repo_part.endswith('.git'):
        return url_repo_part[:-4]

    return url_repo_part


def _set_configuration_key(config, key, value):
    item = next((cfg for cfg in config if cfg['key'] == key), None)
    if item:
        item['value'] = value
    else:
        config.append({'key': key, 'value': value})
    return config


def _config_list_to_dict(config):

    return dict(((cfg['key'], cfg.get('value', '')) for cfg in config))


def _config_dict_to_list(config):

    return [{'key': key, 'value': value} for key, value in config.items()]


def _http_to_gcts_error(func):

    def try_except_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPRequestError as ex:
            raise exception_from_http_error(ex) from ex

    return try_except_wrapper


class _RepositoryHttpProxy:

    def __init__(self, connection, name):
        self.url_prefix = f'repository/{name}'
        self.connection = connection

    def _build_url(self, path):
        url = self.url_prefix
        if path is not None:
            url = f'{url}/{path}'

        return url

    @_http_to_gcts_error
    def get(self, path=None, params=None):
        """Execute HTTP GET."""

        return self.connection.execute('GET', self._build_url(path), params=params)

    @_http_to_gcts_error
    def get_json(self, path=None):
        """Execute HTTP GET with Accept: application/json and get only the JSON part."""

        return self.connection.get_json(self._build_url(path))

    @_http_to_gcts_error
    def post(self, path=None):
        """Execute HTTP POST"""

        return self.connection.execute('POST', self._build_url(path))

    @_http_to_gcts_error
    def post_obj_as_json(self, path, json, accept=None):
        """Execute HTTP POST with content of the given object formatted as JSON"""

        return self.connection.post_obj_as_json(self._build_url(path), json, accept=accept)

    @_http_to_gcts_error
    def delete(self, path=None):
        """Execute HTTP DELETE"""

        return self.connection.execute('DELETE', self._build_url(path))


class Repository:
    """A proxy to gCTS repository"""

    def __init__(self, connection, name, data=None):
        self._http = _RepositoryHttpProxy(connection, name)
        self._name = name
        self._data = data

        self._config = None
        if self._data:
            self._config = self._data.get('config', None)

    def _fetch_data(self):
        mod_log().debug('Fetching data of the repository "%s"', self._name)

        response = self._http.get_json()

        result = response['result']

        mod_log().debug('Fetched data of the repository "%s": %s', self._name, result)

        return result

    def _update_configuration(self, key, value):
        if self._config is None:
            self._config = []

        self._config = _set_configuration_key(self._config, key, value)
        return self._config

    def _get_item(self, item, default=None, fetch=False):
        if self._data is None or fetch:
            self._data = self._fetch_data()

        return self._data.get(item, default)

    def wipe_data(self):
        """Clears cached data"""

        self._data = None
        self._config = None

    @property
    def name(self):
        """Returns the repository's name"""

        return self._name

    @property
    def rid(self):
        """Returns the repository's RID"""

        return self._get_item('rid')

    @property
    def status(self):
        """Returns the repository's status"""

        return self._get_item('status')

    @property
    def vsid(self):
        """Returns the repository's vSID"""

        return self._get_item('vsid')

    @property
    def is_cloned(self):
        """Returns True if the repository is cloned, otherwise False"""

        return self.status != 'CREATED'

    @property
    def url(self):
        """Returns the repository's URL"""

        return self._get_item('url')

    @property
    def branch(self):
        """Returns the repository's current URL"""

        return self._get_item('branch')

    @property
    def head(self):
        """Returns the repository's RID"""

        return self._get_item('currentCommit')

    @property
    def configuration(self):
        """Returns the current repository configuration"""

        if self._config is None:
            self._config = self._get_item('config')

        return _config_list_to_dict(self._config)

    def create(self, url, vsid, config=None, role='SOURCE', typ='GITHUB'):
        """Creates the repository

           Raises:
             GCTSRequestError
             GCTSRepoAlreadyExistsError
        """

        repo = self._data or {}

        repo.update({
            'rid': self._name,
            'name': self._name,
            'vsid': vsid,
            'url': url,
            'role': role,
            'type': typ,
            'connection': 'ssl'
        })

        if config:
            repo_config = _config_list_to_dict(repo.get('config', []))
            repo_config.update(config)
            request_config = _config_dict_to_list(repo_config)
            repo['config'] = request_config

        create_request = {
            'repository': self.name,
            'data': repo
        }

        try:
            response = self._http.connection.post_obj_as_json('repository', create_request, accept='application/json')
        except HTTPRequestError as ex:
            raise exception_from_http_error(ex) from ex

        result = response.json()['repository']
        if self._data:
            self._data.update(result)
        else:
            self._data = result

    def set_config(self, key, value):
        """Sets configuration value

           Raises:
             GCTSRequestError
             GCTSRepoAlreadyExistsError
        """

        self._http.post_obj_as_json('config', {
            'key': key,
            'value': value
        })

        self._update_configuration(key, value)

    def get_config(self, key):
        """Returns configuration value

           Raises:
             GCTSRequestError
             GCTSRepoAlreadyExistsError
        """

        config = self.configuration

        if config is not None and key in config:
            return config[key]

        response = self._http.get_json(f'config/{key}')
        value = response['result']['value']
        self._update_configuration(key, value)
        return value

    def clone(self):
        """Clones the repository on the configured system

           Raises:
             GCTSRequestError
             GCTSRepoAlreadyExistsError
        """

        response = self._http.post('clone')

        self.wipe_data()
        return response

    def checkout(self, branch):
        """Checks out the given branch of the repo on the configured system"""

        response = self._http.get(f'branches/{self.branch}/switch', params={'branch': branch})

        self.wipe_data()
        return response.json()['result']

    def log(self):
        """Returns commits of the repository"""

        json_body = self._http.get_json('getCommit')

        return json_body['commits']

    def pull(self):
        """Pulls the repo on the configured system"""

        json_body = self._http.get_json('pullByCommit')

        self.wipe_data()

        return json_body

    def delete(self):
        """Deletes the repo from the configured system"""

        response = self._http.delete()

        self.wipe_data()
        return response

    def commit_transport(self, corrnr, message, description=None):
        """Turns a transport into a commit"""

        commit = {
            'message': message,
            'autoPush': 'true',
            'objects': [{'object': corrnr, 'type': 'TRANSPORT'}]
        }

        if description:
            commit['description'] = description

        response = self._http.post_obj_as_json('commit', commit)

        self.wipe_data()
        return response

    def set_url(self, url):
        """Sets repository URL"""

        data = self._fetch_data()
        if data['url'] == url:
            return None

        data['url'] = url
        return self._http.post_obj_as_json(None, data)


def simple_fetch_repos(connection):
    """Returns list of repositories in the target systems defined by the given
       connection.
    """

    try:
        response = connection.get_json('repository')
    except HTTPRequestError as ex:
        raise exception_from_http_error(ex) from ex

    result = response.get('result', [])
    return [Repository(connection, repo['name'], data=repo) for repo in result]


# pylint: disable=too-many-arguments
def simple_clone(connection, url, name, vsid='6IT', start_dir='src/', vcs_token=None, error_exists=True,
                 role='SOURCE', typ='GITHUB'):
    """Creates and clones the repository in the target systems"""

    config = {}

    if start_dir:
        config['VCS_TARGET_DIR'] = start_dir

    if vcs_token:
        config['CLIENT_VCS_AUTH_TOKEN'] = vcs_token

    repo = Repository(connection, name)

    try:
        repo.create(url, vsid, config=config, role=role, typ=typ)
    except GCTSRepoAlreadyExistsError as ex:
        if error_exists:
            raise ex

        mod_log().debug(ex)
        mod_log().info(str(ex))

        repo.wipe_data()

    if not repo.is_cloned:
        repo.clone()
    else:
        mod_log().info('Not cloning the repository "%s": already performed')

    return repo


def simple_checkout(connection, branch, name=None, repo=None):
    """Checks out the given branch in the given repository on the give system"""

    if repo is None:
        repo = Repository(connection, name)

    return repo.checkout(branch)


def simple_log(connection, name=None, repo=None):
    """Returns log history of the given repository on the give system"""

    if repo is None:
        repo = Repository(connection, name)

    return repo.log()


def simple_pull(connection, name=None, repo=None):
    """Pulls the given repository on the give system"""

    if repo is None:
        repo = Repository(connection, name)

    return repo.pull()


def simple_delete(connection, name):
    """Deletes the given repository on the give system"""

    return Repository(connection, name).delete()


def simple_set_user_api_token(connection, api_url, token):
    """Set Token for the currently logged in user"""

    body = {
        'endpoint': api_url,
        'user': '',
        'password': '',
        'token': token,
        'type': 'token'
    }

    connection.post_obj_as_json('user/credentials', body)
