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

"""This module handles triggering Kokoro release jobs for merged release pull requests."""

from autorelease import common, github, kokoro, reporter
from releasetool.commands import tag

LANGUAGE_ALLOWLIST = ["java"]
ORGANIZATIONS_TO_SCAN = ["googleapis", "GoogleCloudPlatform"]


def trigger_kokoro_build_for_pull_request(
    kokoro_session, gh: github.GitHub, issue: dict, result
) -> None:
    """Triggers the Kokoro job for a given pull request if possible.

    If the pull request is not merged, remove the `autorelease: pending` label
    and mark it as closed. Otherwise, determine the name of the Kokoro job
    name and trigger a build.
    """
    # Reify the "issue" into a full pull request object from github. This
    # is necessary because github gives us back an issue object, but it
    # doesn't contain all of the PR info.
    pull = gh.get_url(issue["pull_request"]["url"])

    # Before doing any processing, check to make sure the PR was actually merged.
    # "closed" PRs can be merged or just closed without merging.
    if not pull.get("merged_at"):
        result.skipped = True
        result.print("Closed, not merged, skipping.")
        # Remove the label so we don't continue processing it.
        gh.update_pull_labels(
            pull, add=["autorelease: closed"], remove=["autorelease: pending"]
        )
        return

    # Determine language.
    lang = common.guess_language(gh, pull["base"]["repo"]["full_name"])

    # As part of the migration to release-please tagging, cross-reference the
    # language against an allowlist to allow migrating language-by-language.
    if lang not in LANGUAGE_ALLOWLIST:
        result.skipped = True
        result.print(f"Language {lang} not in allowlist, skipping.")
        return

    language_module = getattr(tag, lang)
    package_name = language_module.package_name(pull)
    kokoro_job_name = language_module.kokoro_job_name(
        pull["base"]["repo"]["full_name"], package_name
    )
    pull_request_url = pull["html_url"]
    if kokoro_job_name is None:
        result.skipped = True
        result.print(f"No Kokoro job for {pull_request_url}, skipping.")
        return

    sha = pull["merge_commit_sha"]

    # Trigger Kokoro release build
    result.print(f"Triggering {kokoro_job_name} using {sha}")
    kokoro.trigger_build(
        kokoro_session,
        job_name=kokoro_job_name,
        sha=sha,
        env_vars={"AUTORELEASE_PR": pull_request_url},
    )


def main(github_token, kokoro_credentials) -> reporter.Reporter:
    report = reporter.Reporter("autorelease.trigger")
    # TODO(busunkim): Use proxy once KMS setup is complete.
    gh = github.GitHub(github_token, use_proxy=False)
    kokoro_session = kokoro.make_authorized_session(kokoro_credentials)

    # First, we need to get a list of all pull requests (GitHub calls these "issues")
    # that are merged ("closed") and have the label "autorelease: tagged".
    list_result = reporter.Result("list issues")
    report.add(list_result)

    all_issues = []
    for org in ORGANIZATIONS_TO_SCAN:
        try:
            issues = gh.list_org_issues(
                org=org,
                # Must be merged ("closed").
                state="closed",
                # Must be labeled with "autorelease: pending"
                labels="autorelease: tagged",
            )

            # Just in case any non-PRs got in here.
            issues = [result for result in issues if "pull_request" in result]

            all_issues.extend(issues)

        # Exceptions while getting the list of pull requests constitutes a total failure.
        except Exception as exc:
            list_result.error = True
            list_result.print(exc)

    # Print out our findings as a checkpoint.
    list_result.print("Working set:")
    for issue in all_issues:
        list_result.print(f" * {issue['title']}: {issue['pull_request']['html_url']}")

    # For each pull request, execute releasetool tag for it.
    for issue in all_issues:
        result = reporter.Result(f"{issue['title']}")
        report.add(result)
        result.print(
            f"Processing {issue['title']}: {issue['pull_request']['html_url']}"
        )

        try:
            trigger_kokoro_build_for_pull_request(kokoro_session, gh, issue, result)
        # Failing any one PR is fine, just record it in the log and continue.
        except Exception as exc:
            result.error = True
            result.print(f"{exc!r}")

    return report
