# Copyright 2021 Google LLC
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

from unittest.mock import patch, Mock

from autorelease import trigger


@patch("autorelease.trigger.trigger_kokoro_build_for_pull_request")
@patch("autorelease.github.GitHub.list_org_issues")
@patch("autorelease.kokoro.make_authorized_session")
def test_no_issues(
    make_authorized_session, list_org_issues, trigger_kokoro_build_for_pull_request
):
    list_org_issues.return_value = []

    trigger.main("github-token", "kokoro-credentials")
    make_authorized_session.assert_called_once()
    trigger_kokoro_build_for_pull_request.assert_not_called()


@patch("autorelease.trigger.trigger_kokoro_build_for_pull_request")
@patch("autorelease.github.GitHub.list_org_issues")
@patch("autorelease.kokoro.make_authorized_session")
def test_processes_issues(
    make_authorized_session, list_org_issues, trigger_kokoro_build_for_pull_request
):
    pr1 = {
        "base": {"ref": "abc123", "repo": {"full_name": "googleapis/java-asset"}},
        "pull_request": {"html_url": "https://github.com/googleapis/java-asset"},
        "title": "chore: release 1.2.3",
    }
    pr2 = {
        "base": {"ref": "def456", "repo": {"full_name": "googleapis/nodejs-container"}},
        "pull_request": {"html_url": "https://github.com/nodejs/java-container"},
        "title": "chore: release 1.0.0",
    }
    list_org_issues.side_effect = [[pr1, pr2]]
    trigger.main("github-token", "kokoro-credentials")
    list_org_issues.assert_any_call(
        org="googleapis",
        state="closed",
        labels="autorelease: tagged",
        created_after="2021-04-01",
    )
    list_org_issues.assert_any_call(
        org="GoogleCloudPlatform",
        state="closed",
        labels="autorelease: tagged",
        created_after="2021-04-01",
    )
    assert trigger_kokoro_build_for_pull_request.call_count == 2


@patch("autorelease.kokoro.trigger_build")
def test_trigger_kokoro_build_for_pull_request_skips_non_merged(trigger_build):
    github = Mock()
    github.update_pull_labels = Mock()
    github.get_url.return_value = {
        "merged_at": None,
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
    }
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"}
    }
    trigger.trigger_kokoro_build_for_pull_request(Mock(), github, issue, Mock())
    github.update_pull_labels.assert_called_once()
    trigger_build.assert_not_called()


@patch("autorelease.trigger.LANGUAGE_ALLOWLIST", ["java"])
@patch("autorelease.kokoro.trigger_build")
def test_trigger_kokoro_build_for_pull_request_triggers_kokoro(trigger_build):
    github = Mock()
    github.get_url.return_value = {
        "merged_at": "2021-01-01T09:00:00.000Z",
        "merge_commit_sha": "abcd1234",
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
        "html_url": "https://github.com/googleapis/java-asset/pulls/5",
    }
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"},
        "merged_at": "2021-01-01T09:00:00.000Z",
    }

    trigger.trigger_kokoro_build_for_pull_request(Mock(), github, issue, Mock())
    trigger_build.assert_called_once()


@patch("autorelease.trigger.LANGUAGE_ALLOWLIST", [])
@patch("autorelease.kokoro.trigger_build")
def test_trigger_kokoro_build_for_pull_request_skips_kokoro_if_not_in_allowlist(
    trigger_build,
):
    github = Mock()
    github.get_url.return_value = {
        "merged_at": "2021-01-01T09:00:00.000Z",
        "merge_commit_sha": "abcd1234",
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
        "html_url": "https://github.com/googleapis/java-asset/pulls/5",
    }
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"},
        "merged_at": "2021-01-01T09:00:00.000Z",
    }
    trigger.trigger_kokoro_build_for_pull_request(Mock(), github, issue, Mock())
    trigger_build.assert_not_called()


@patch("autorelease.trigger.LANGUAGE_ALLOWLIST", ["php"])
@patch("autorelease.kokoro.trigger_build")
def test_trigger_kokoro_build_for_pull_request_skips_kokoro_if_no_job_name(
    trigger_build,
):
    github = Mock()
    github.get_url.return_value = {
        "merged_at": "2021-01-01T09:00:00.000Z",
        "base": {"repo": {"full_name": "googleapis/google-cloud-php"}},
        "html_url": "https://github.com/googleapis/google-cloud-php/pulls/5",
    }
    issue = {
        "pull_request": {
            "url": "https://api.github.com/googleapis/google-cloud-php/pull/5"
        },
        "merged_at": "2021-01-01T09:00:00.000Z",
    }
    trigger.trigger_kokoro_build_for_pull_request(Mock(), github, issue, Mock())
    trigger_build.assert_not_called()
