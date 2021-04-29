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

import requests_mock
from unittest.mock import patch, Mock

from autorelease import tag


@patch("autorelease.tag.process_issue")
@patch("autorelease.github.GitHub.list_org_issues")
@patch("autorelease.kokoro.make_authorized_session")
def test_no_issues(make_authorized_session, list_org_issues, process_issue):
    list_org_issues.return_value = []

    tag.main("github-token", "kokoro-credentials")
    make_authorized_session.assert_called_once()
    process_issue.assert_not_called()


@patch("autorelease.tag.process_issue")
@patch("autorelease.github.GitHub.list_org_issues")
@patch("autorelease.kokoro.make_authorized_session")
def test_processes_issues(make_authorized_session, list_org_issues, process_issue):
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
    tag.main("github-token", "kokoro-credentials")
    list_org_issues.assert_any_call(
        org="googleapis", state="closed", labels="autorelease: pending"
    )
    list_org_issues.assert_any_call(
        org="GoogleCloudPlatform", state="closed", labels="autorelease: pending"
    )
    assert process_issue.call_count == 2


@patch("releasetool.commands.tag.java.tag")
def test_run_releasetool_tag_delegates(tag_mock):
    github = Mock()
    github.token = "github-token"
    context = Mock()
    tag_mock.return_value = context
    pull = {"base": {"ref": "abc123", "repo": {"full_name": "googleapis/java-asset"}}}
    ctx = tag.run_releasetool_tag("java", github, pull)
    assert ctx == context


@patch("autorelease.tag.run_releasetool_tag")
def test_process_issue_skips_non_merged(run_releasetool_tag):
    github = Mock()
    github.update_pull_labels = Mock()
    github.get_url.return_value = {
        "merged_at": None,
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
    }
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"}
    }
    tag.process_issue(Mock(), github, issue, Mock())
    github.update_pull_labels.assert_called_once()
    run_releasetool_tag.assert_not_called()


@patch("autorelease.tag.LANGUAGE_ALLOWLIST", ["java"])
@patch("autorelease.kokoro.trigger_build")
@patch("autorelease.tag.run_releasetool_tag")
def test_process_issue_triggers_kokoro(run_releasetool_tag, trigger_build):
    github = Mock()
    github.get_url.return_value = {
        "merged_at": "2021-01-01T09:00:00.000Z",
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
        "html_url": "https://github.com/googleapis/java-asset/pulls/5",
    }
    context = Mock()
    context.kokoro_job_name = "kokoro-job-name"
    context.release_tag = "v1.2.3"
    run_releasetool_tag.return_value = context
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"},
        "merged_at": "2021-01-01T09:00:00.000Z",
    }
    tag.process_issue(Mock(), github, issue, Mock())
    run_releasetool_tag.assert_called_once()
    trigger_build.assert_called_once()


@patch("autorelease.tag.LANGUAGE_ALLOWLIST", ["java"])
@patch("autorelease.kokoro.trigger_build")
@patch("autorelease.tag.run_releasetool_tag")
def test_process_issue_skips_kokoro_if_no_job_name(run_releasetool_tag, trigger_build):
    github = Mock()
    github.get_url.return_value = {
        "merged_at": "2021-01-01T09:00:00.000Z",
        "base": {"repo": {"full_name": "googleapis/java-asset"}},
        "html_url": "https://github.com/googleapis/java-asset/pulls/5",
    }
    context = Mock()
    context.kokoro_job_name = None
    context.release_tag = None
    run_releasetool_tag.return_value = context
    issue = {
        "pull_request": {"url": "https://api.github.com/googleapis/java-asset/pull/5"},
        "merged_at": "2021-01-01T09:00:00.000Z",
    }
    tag.process_issue(Mock(), github, issue, Mock())
    run_releasetool_tag.assert_called_once()
    trigger_build.assert_not_called()


@patch("autorelease.tag.LANGUAGE_ALLOWLIST", ["java"])
@patch("autorelease.tag.run_releasetool_tag")
@patch("autorelease.github.GitHub.list_org_issues")
@patch("autorelease.kokoro.make_authorized_session")
def test_respects_allowlist(
    make_authorized_session, list_org_issues, run_releasetool_tag
):
    pr1 = {
        "base": {"ref": "abc123", "repo": {"full_name": "googleapis/java-asset"}},
        "pull_request": {
            "url": "https://api.github.com/repos/googleapis/java-asset/pull/123",
            "html_url": "https://github.com/googleapis/java-asset",
        },
        "title": "chore: release 1.2.3",
    }
    pr2 = {
        "base": {"ref": "def456", "repo": {"full_name": "googleapis/nodejs-container"}},
        "pull_request": {
            "url": "https://api.github.com/repos/googleapis/nodejs-container/pull/234",
            "html_url": "https://github.com/nodejs/nodejs-container",
        },
        "title": "chore: release 1.0.0",
    }
    list_org_issues.side_effect = [[pr1, pr2]]
    with requests_mock.Mocker() as m:
        m.get(
            "https://api.github.com/repos/googleapis/java-asset/pull/123",
            json={
                "merged_at": "2021-01-01T09:00:00.000Z",
                "base": {"repo": {"full_name": "googleapis/java-asset"}},
            },
        )
        m.get(
            "https://api.github.com/repos/googleapis/nodejs-container/pull/234",
            json={
                "merged_at": "2021-01-01T09:00:00.000Z",
                "base": {"repo": {"full_name": "googleapis/nodejs-container"}},
            },
        )
        tag.main("github-token", "kokoro-credentials")
    list_org_issues.assert_any_call(
        org="googleapis", state="closed", labels="autorelease: pending"
    )
    list_org_issues.assert_any_call(
        org="GoogleCloudPlatform", state="closed", labels="autorelease: pending"
    )
    assert run_releasetool_tag.call_count == 1
