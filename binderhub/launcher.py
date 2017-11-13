"""
Launch an image with a temporary user via JupyterHub
"""
import base64
import json
import random
import re
import string
from urllib.parse import urlparse
import uuid

from tornado.log import app_log
from tornado import web, gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError
from traitlets.config import LoggingConfigurable
from traitlets import Unicode

# pattern for checking if it's an ssh repo and not a URL
# used only after verifying that `://` is not present
_ssh_repo_pat = re.compile(r'.*@.*\:')

# Add a random lowercase alphanumeric suffix to usernames to avoid collisions
# Set of characters from which to generate a suffix
SUFFIX_CHARS = string.ascii_lowercase + string.digits
# Set length of suffix. Number of combinations = SUFFIX_CHARS**SUFFIX_LENGTH = 36**8 ~= 2**41
SUFFIX_LENGTH = 8

class Launcher(LoggingConfigurable):
    """Object for encapsulating launching an image for a user"""

    hub_api_token = Unicode(help="The API token for the Hub")
    hub_url = Unicode(help="The URL of the Hub")

    async def api_request(self, url, *args, **kwargs):
        """Make an API request to JupyterHub"""
        headers = kwargs.setdefault('headers', {})
        headers.update({'Authorization': 'token %s' % self.hub_api_token})
        req = HTTPRequest(self.hub_url + 'hub/api/' + url, *args, **kwargs)
        resp = await AsyncHTTPClient().fetch(req)
        # TODO: handle errors
        return resp

    def username_from_repo(self, repo):
        """Generate a username for a git repo url

        e.g. minrk-binder-example-abc123
        from https://github.com/minrk/binder-example.git
        """
        # start with url path
        print
        if '://' not in repo and _ssh_repo_pat.match(repo):
            # ssh url
            path = repo.split(':', 1)[1]
        else:
            path = urlparse(repo).path

        prefix = path.strip('/').replace('/', '-').lower()

        if prefix.endswith('.git'):
            # strip trailing .git
            prefix = prefix[:-4]

        if len(prefix) > 32:
            # if it's long, truncate
            prefix = '{}-{}'.format(prefix[:15], prefix[-15:])

        # add a random suffix to avoid collisions for users on the same image
        return '{}-{}'.format(prefix, ''.join(random.choices(SUFFIX_CHARS, k=SUFFIX_LENGTH)))

    async


    async def abort_launch(self, username, server=False):
        """Abort a launch

        if server: server was requested and must be shutdown prior to deleting the user
        """
        if server:
            app_log.info("Shutting down unused server for %s", username)
            # Need to halt the server.
            # This can get hairy if it's still launching.
            resp = await self.api_request('users/%s/server' % username, method='DELETE')
            if resp.code == 202:
                # Server hasn't actually stopped yet
                # We wait for it!
                def check():
                    resp = await self.api_request(
                        'users/%s' % username,
                        method='GET',
                    )

                    body = json.loads(resp.body.decode('utf-8'))
                    if body['server'] or body['pending']:
                        return False
                    return True
                await exponential_backoff(
                    check,
                    fail_message="Image %s for user %s took too long to stop" % (image, username),
                    timeout=self.settings.get('launch_timeout', 300),
                )


            # wait for server
        # delete the user
        app_log.info("Deleting unused user %s", username)
        await self.api_request('users/' + username, method='DELETE')
        user = await


    async def launch(self, image, username, abort_future=None):
        """Launch a server for a given image


        - creates the user on the Hub
        - spawns a server for that user
        - generates a token
        - returns a dict containing:
          - `url`: the URL of the server
          - `token`: the token for the server
        """
        # TODO: validate the image argument?

        server_requested = False
        async def maybe_abort():
            if abort_future and abort_future.done():
                await abort_launch(username, server=server_requested)
                return True
            return False

        def should_abort():
            """Check if abort_future has been triggered and we should stop"""
            return abort_future and abort_future.done()

        # create a new user
        app_log.info("Creating user %s for image %s", username, image)
        try:
            await self.api_request('users/%s' % username, body=b'', method='POST')
        except HTTPError as e:
            if e.response:
                body = e.response.body
            else:
                body = ''
            app_log.error("Error creating user %s: %s\n%s",
                username, e, body,
            )
            raise web.HTTPError(500, "Failed to create temporary user for %s" % image)

        if should_abort():
            app_log.warning("Aborting prior to launch: %r", username)
            await self.abort_launch(username, server=False)
            return

        # generate a token
        token = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode('ascii').rstrip('=\n')

        # start server
        app_log.info("Starting server for user %s with image %s", username, image)
        try:
            resp = await self.api_request(
                'users/%s/server' % username,
                method='POST',
                body=json.dumps({
                    'token': token,
                    'image': image,
                }).encode('utf8'),
            )
            if resp.code == 202:
                # Server hasn't actually started yet
                # We wait for it!

                def wait_up():
                    resp = await self.api_request(
                        'users/%s' % username,
                        method='GET',
                    )

                    body = json.loads(resp.body.decode('utf-8'))
                    if body['server']:
                        return True
                    if should_abort():
                        return True
                    return False

                # FIXME: Measure how long it takes for servers to start
                # and tune this appropriately
                await exponential_backoff(
                    wait_up,
                    fail_message="Image %s for user %s took too long to launch" % (image, username),
                    timeout=self.settings.get('launch_timeout', 300),
                )

        except HTTPError as e:
            if e.response:
                body = e.response.body
            else:
                body = ''

            app_log.error("Error starting server for %s: %s\n%s",
                username, e, body,
            )
            raise web.HTTPError(500, "Failed to launch image %s" % image)

        if should_abort():
            app_log.warning("Aborting unfinished launch: %r", username)
            await self.abort_launch(username, server=True)
            return

        url = self.hub_url + 'user/%s/' % username

        return {
            'url': url,
            'token': token,
        }
