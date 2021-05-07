# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import logging
import os
from typing import Dict, List, Sequence, Generator

import requests
from urllib3.util.retry import Retry
from urllib.parse import quote

_GITHUB_ROOT: str = "https://api.github.com"
_MAGIC_GITHUB_PROXY_ROOT: str = (
    "https://magic-github-proxy.endpoints.devrel-prod.cloud.goog"
)


def _find_devrel_api_key() -> str:
    paths: List[str] = []
    magic_github_proxy_key: str = ""
    if "KOKORO_KEYSTORE_DIR" in os.environ:
        paths.append(
            os.path.join(
                os.environ["KOKORO_KEYSTORE_DIR"], "73713_magic-github-proxy-api-key"
            )
        )

    if "KOKORO_GFILE_DIR" in os.environ:
        paths.append(
            os.path.join(
                os.environ["KOKORO_GFILE_DIR"], "yoshi-magic-github-proxy-key.txt"
            )
        )

    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                magic_github_proxy_key = fh.read().strip()
                break

    if magic_github_proxy_key == "":
        raise Exception("A magic github proxy api key is required.")

    return magic_github_proxy_key


class GitHub:
    def __init__(self, token: str, use_proxy: bool = False) -> None:
        self.token: str = token
        self.session: requests.Session = requests.Session()
        self.GITHUB_ROOT = _GITHUB_ROOT
        self.session.headers.update(
            {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"Bearer {token}",
            }
        )

        if use_proxy:
            self.GITHUB_ROOT = _MAGIC_GITHUB_PROXY_ROOT
            # To use the proxy, we need an api key for the magic github proxy.
            self.session.params = {"key": _find_devrel_api_key()}

    def get_url(self, url: str = None, **kwargs) -> dict:
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def list_org_repos(self, org: str, type: str = None) -> Generator[dict, None, None]:
        url = f"{self.GITHUB_ROOT}/orgs/{org}/repos"

        while url:
            response = self.session.get(url, params={"type": type})
            response.raise_for_status()
            for item in response.json():
                yield item

            url = response.links.get("next", {}).get("url")

    def list_org_issues(
        self, org: str, state: str = None, labels: str = None, created_after: str = None
    ) -> Generator[dict, None, None]:
        url = f"{self.GITHUB_ROOT}/search/issues?q=org:{quote(org)}+state:{quote(state)}+archived:false"
        if labels:
            # Note: GitHub query API expects label to be enclosed in quotes:
            quotedLabels = '"' + labels + '"'
            url += f"+label:{quote(quotedLabels)}"
        if created_after:
            url += f"+created:>{created_after}"
        print(url)
        # GitHub sometimes returns 5xx errors for this request.
        # Retry after 500, 502 response up to 4 times.
        max_retries = Retry(status=4, status_forcelist=[500, 502])
        adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        self.session.mount(url, adapter)

        while url:
            response = self.session.get(url)
            response.raise_for_status()
            if response.status_code >= 400:
                logging.error(response.text)
            for item in response.json()["items"]:
                yield item

            url = response.links.get("next", {}).get("url")

    def list_pull_requests(self, repository: str, **kwargs) -> Sequence[Dict]:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/pulls"
        response = self.session.get(url, params=kwargs)
        response.raise_for_status()
        return response.json()

    def create_pull_request(
        self, repository: str, branch: str, title: str, body: str = None
    ) -> dict:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/pulls"
        response = self.session.post(
            url,
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": "master",
                "maintainer_can_modify": True,
            },
        )
        response.raise_for_status()
        return response.json()

    def replace_issue_labels(
        self, owner: str, repository: str, number: str, labels: Sequence[str]
    ) -> dict:
        url = f"{self.GITHUB_ROOT}/repos/{owner}/{repository}/issues/{number}/labels"
        response = self.session.put(url, json={"labels": labels})
        response.raise_for_status()
        return response.json()

    def update_pull_labels(
        self, pull: dict, add: Sequence[str] = None, remove: Sequence[str] = None
    ) -> dict:
        """Updates labels for a github pull, adding and removing labels as needed."""
        label_names = set([label["name"] for label in pull["labels"]])

        if add:
            label_names = label_names.union(add)

        if remove:
            label_names = label_names.difference(remove)

        return self.replace_issue_labels(
            owner=pull["base"]["repo"]["owner"]["login"],
            repository=pull["base"]["repo"]["name"],
            number=pull["number"],
            labels=list(label_names),
        )

    def get_tree(self, repository: str, tree_sha: str = "master") -> Sequence[dict]:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/git/trees/{tree_sha}"
        response = self.session.get(url, params={})
        response.raise_for_status()
        return response.json()

    def get_contents(self, repository: str, path: str, ref: str = None) -> bytes:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/contents/{path}"
        response = self.session.get(url, params={"ref": ref})
        response.raise_for_status()
        return base64.b64decode(response.json()["content"])

    def list_files(self, repository: str, path: str, ref: str = None) -> Sequence[dict]:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/contents/{path}"
        response = self.session.get(url, params={"ref": ref})
        response.raise_for_status()
        return response.json()

    def check_for_file(self, repository: str, path: str, ref: str = None) -> bool:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/contents/{path}"
        response = self.session.head(url, params={"ref": ref})

        if response.status_code == 200:
            return True
        else:
            return False

    def create_release(
        self,
        repository: str,
        tag_name: str,
        target_commitish: str,
        name: str,
        body: str,
    ) -> Dict:
        url = f"{self.GITHUB_ROOT}/repos/{repository}/releases"
        response = self.session.post(
            url,
            json={
                "tag_name": tag_name,
                "target_commitish": target_commitish,
                "name": name,
                "body": body,
            },
        )
        response.raise_for_status()
        return response.json()

    def create_pull_request_comment(
        self, repository: str, pull_request_number: int, comment: str
    ) -> Dict:
        repo_url = f"{self.GITHUB_ROOT}/repos/{repository}"
        url = f"{repo_url}/issues/{pull_request_number}/comments"
        response = self.session.post(url, json={"body": comment})
        response.raise_for_status()
        return response.json()

    def get_languages(self, repository) -> Dict[str, int]:
        """Returns the # of lines of code of each programming language in the repo.

        See: https://developer.github.com/v3/repos/#list-repository-languages

        Args:
            repository {str} -- GitHub repository with the format [owner]/[repo]

        Returns:
            Dict[str, int]: Map of programming language to lines of code.
        """
        url = f"{self.GITHUB_ROOT}/repos/{repository}/languages"
        langs: Dict[str, int] = {}

        while url:
            response = self.session.get(url)
            langs.update(response.json())
            url = response.links.get("next", {}).get("url")
        return langs
