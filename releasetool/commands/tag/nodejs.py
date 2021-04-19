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

import getpass
import re
from typing import Union

import click

import releasetool.circleci
import releasetool.git
import releasetool.github
import releasetool.secrets
import releasetool.commands.common
from releasetool.commands.common import TagContext
import subprocess
import tempfile

# Repos that have their publication process handled by GitHub actions:
manifest_release = [
    "googleapis/google-api-nodejs-client",
    "googleapis/repo-automation-bots",
]


def determine_release_pr(ctx: TagContext) -> None:
    click.secho(
        "> Let's figure out which pull request corresponds to your release.", fg="cyan"
    )

    pulls = ctx.github.list_pull_requests(ctx.upstream_repo, state="closed")
    pulls = [pull for pull in pulls if "release" in pull["title"].lower()][:30]

    click.secho("> Please pick one of the following PRs:\n")
    for n, pull in enumerate(pulls, 1):
        print(f"\t{n}: {pull['title']} ({pull['number']})")

    pull_idx = click.prompt("\nWhich one do you want to tag and release?", type=int)

    ctx.release_pr = pulls[pull_idx - 1]


def determine_release_tag(ctx: TagContext) -> None:
    click.secho("> Determining what the release tag should be.", fg="cyan")
    head_ref = ctx.release_pr["head"]["ref"]
    match = re.match("release-(.+)", head_ref)

    if match is not None:
        ctx.release_tag = match.group(1)
    else:
        click.secho(
            "I couldn't determine what the release tag should be from the PR's"
            f"head ref {head_ref}.",
            fg="red",
        )
        ctx.release_tag = click.prompt(
            "What should the release tag be (for example, storage-1.2.3)?"
        )

    click.secho(f"Release tag is {ctx.release_tag}.")


def determine_package_version(ctx: TagContext) -> None:
    click.secho("> Determining the package version.", fg="cyan")
    match = re.match(r"(?P<version>v?\d+\.\d+\.\d+)", ctx.release_tag)
    ctx.release_version = match.group("version")
    click.secho(f"package version: {ctx.release_version}.")


def get_release_notes(ctx: TagContext) -> None:
    click.secho("> Grabbing the release notes.")
    changelog = ctx.github.get_contents(
        ctx.upstream_repo, "CHANGELOG.md", ref=ctx.release_pr["merge_commit_sha"]
    ).decode("utf-8")

    _get_latest_release_notes(ctx, changelog)


def _get_latest_release_notes(ctx: TagContext, changelog: str):
    # the 'v' prefix is not used in the conventional-changelog templates
    # used in automated CHANGELOG generation:
    version = re.sub(r"^v", "", ctx.release_version)
    match = re.search(
        rf"## v?\[?{version}[^\n]*\n(?P<notes>.+?)(\n##\s|\n### \[?[0-9]+\.|\Z)",
        changelog,
        re.DOTALL | re.MULTILINE,
    )
    if match is not None:
        ctx.release_notes = match.group("notes").strip()
    else:
        ctx.release_notes = ""


def create_release(ctx: TagContext) -> None:
    click.secho("> Creating the release.")
    default_branch = ctx.release_pr["base"]["ref"]
    repo = ctx.release_pr["base"]["repo"]["full_name"]
    with tempfile.NamedTemporaryFile("w+t", delete=False) as fp:
        fp.write(ctx.token)
        token_file = fp.name

    if ctx.upstream_repo in manifest_release:
        # delegate release tagging to release-please

        subprocess.check_output(
            [
                "npx",
                "release-please",
                "manifest-release",
                f"--token={token_file}",
                f"--default-branch={default_branch}",
                f"--repo-url={repo}",
                "--debug",
            ]
        )
    else:
        subprocess.check_output(
            [
                "npx",
                "release-please",
                "github-release",
                f"--token={token_file}",
                f"--repo-url={repo}",
            ]
        )

        release_location_string = f"Release is at {ctx.github_release['html_url']}"
        click.secho(release_location_string)
        click.secho("CI will handle publishing the package to npm.")

        ctx.github.create_pull_request_comment(
            ctx.upstream_repo, ctx.release_pr["number"], release_location_string
        )

        ctx.github.update_pull_labels(
            ctx.release_pr, add=["autorelease: tagged"], remove=["autorelease: pending"]
        )


def wait_on_circle(ctx: TagContext) -> None:
    circle = releasetool.circleci.CircleCI(repository=ctx.upstream_repo)
    click.secho("> Waiting for CircleCI to queue a release build")
    tag_name = ctx.release_version
    fresh_build = circle.get_latest_build_by_tag(tag_name)
    if fresh_build:
        click.secho(f"CircleCI Build: {fresh_build['build_url']}")
        click.secho("> Monitoring CircleCI for completion of release")
        click.secho("")
        for state in circle.get_build_status_generator(fresh_build["build_num"]):
            click.secho(f"CircleCI Build State: {state}\r", nl=False)
    else:
        click.secho(f"CircleCI Build not found for tag {tag_name}...")


def kokoro_job_name(upstream_repo: str, package_name: str) -> Union[str, None]:
    """Return the Kokoro job name.

    Args:
        upstream_repo (str): The GitHub repo in the form of `<owner>/<repo>`
        package_name (str): The name of package to release

    Returns:
        The name of the Kokoro job to trigger or None if there is no job to trigger
    """
    return f"cloud-devrel/client-libraries/nodejs/release/{upstream_repo}/publish"


def tag(ctx: TagContext = None) -> TagContext:
    if not ctx:
        ctx = TagContext()

    if ctx.interactive:
        click.secho(f"o/ Hey, {getpass.getuser()}, let's tag a release!", fg="magenta")

    if ctx.github is None:
        releasetool.commands.common.setup_github_context(ctx)

    if ctx.release_pr is None:
        determine_release_pr(ctx)

    # If using manifest release, the manifest releaser determines
    # release tag, version, and release notes:
    if ctx.upstream_repo not in manifest_release:
        determine_release_tag(ctx)
        determine_package_version(ctx)
        # If the release already exists, don't do anything
        if releasetool.commands.common.release_exists(ctx):
            click.secho(f"{ctx.release_tag} already exists.", fg="magenta")
            return ctx
        get_release_notes(ctx)
    else:
        # If using mono-release strategy, fallback to using sha from
        # time of merge:
        ctx.release_tag = ctx.release_pr["merge_commit_sha"]

    create_release(ctx)
    ctx.kokoro_job_name = kokoro_job_name(ctx.upstream_repo, ctx.package_name)
    releasetool.commands.common.publish_via_kokoro(ctx)

    if ctx.interactive:
        click.secho("\\o/ All done!", fg="magenta")

    return ctx
