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
import os
import textwrap
from typing import Optional

import attr
import click
import datetime
import glob

import releasetool.filehelpers
import releasetool.git
import releasetool.github
import releasetool.secrets
import releasetool.commands.common


_CHANGELOG_TEMPLATE = """\
# Release History

[RubyGems.org history][1]

[1]: https://rubygems.org/gems/{package_name}/versions

"""


@attr.s(auto_attribs=True, slots=True)
class Context(releasetool.commands.common.GitHubContext):
    last_release_version: Optional[str] = None
    last_release_committish: Optional[str] = None
    release_version: Optional[str] = None
    release_branch: Optional[str] = None
    pull_request: Optional[dict] = None
    version_file: Optional[str] = None
    today: str = datetime.date.today().__str__()


def determine_package_name(ctx: Context) -> None:
    click.secho("> Figuring out the package name.", fg="cyan")
    ctx.package_name = os.path.basename(os.getcwd())
    click.secho(f"Looks like we're releasing {ctx.package_name}.")


def determine_last_release(ctx: Context) -> None:
    click.secho("> Figuring out what the last release was.", fg="cyan")
    tags = releasetool.git.list_tags()
    candidates = [tag for tag in tags if tag.startswith(ctx.package_name)]

    if candidates:
        ctx.last_release_committish = candidates[0]
        ctx.last_release_version = candidates[0].rsplit("/").pop().lstrip("v")

    else:
        click.secho(
            f"I couldn't figure out the last release for {ctx.package_name}, "
            "so I'm assuming this is the first release. Can you tell me "
            "which git rev/sha to start the changelog at?",
            fg="yellow",
        )
        ctx.last_release_committish = click.prompt("Committish")
        ctx.last_release_version = "0.0.0"

    click.secho(f"The last release was {ctx.last_release_version}.")


def gather_changes(ctx: Context) -> None:
    click.secho(f"> Gathering changes since {ctx.last_release_version}", fg="cyan")
    ctx.changes = releasetool.git.summary_log(
        from_=ctx.last_release_committish, to=f"{ctx.upstream_name}/master"
    )
    click.secho(f"Cool, {len(ctx.changes)} changes found.")


def edit_release_notes(ctx: Context) -> None:
    click.secho("> Opening your editor to finalize release notes.", fg="cyan")
    release_notes = "\n".join(f"* {change}" for change in ctx.changes)
    ctx.release_notes = releasetool.filehelpers.open_editor_with_tempfile(
        release_notes, "release-notes.md"
    ).strip()


def determine_release_version(ctx: Context) -> None:
    click.secho("> Now it's time to pick a release version!", fg="cyan")
    release_notes = textwrap.indent(ctx.release_notes, "\t")
    click.secho(f"Here's the release notes you wrote:\n\n{release_notes}\n")

    parsed_version = [int(x) for x in ctx.last_release_version.split(".")]

    if parsed_version == [0, 0, 0]:
        ctx.release_version = "0.1.0"
        return

    selection = click.prompt(
        "Is this a major, minor, or patch update (or enter the new version " "directly)"
    )
    if selection == "major":
        parsed_version[0] += 1
        parsed_version[1] = 0
        parsed_version[2] = 0
    elif selection == "minor":
        parsed_version[1] += 1
        parsed_version[2] = 0
    elif selection == "patch":
        parsed_version[2] += 1
    else:
        ctx.release_version = selection
        return

    ctx.release_version = "{}.{}.{}".format(*parsed_version)

    click.secho(f"Got it, releasing {ctx.release_version}.")


def create_release_branch(ctx) -> None:
    ctx.release_branch = f"releases-{ctx.today}"
    current_branch = releasetool.git.get_current_branch()
    click.secho(f"> Current branch is {current_branch}", fg="cyan")
    if current_branch == ctx.release_branch:
        click.secho(f"> Using branch {current_branch}", fg="cyan")
    elif current_branch != "master" and click.confirm(f"Use {current_branch}?"):
        click.secho(f"> Using branch {current_branch}", fg="cyan")
    else:
        click.secho(f"> Creating branch {ctx.release_branch}", fg="cyan")
        return releasetool.git.checkout_create_branch(ctx.release_branch)


def update_changelog(ctx: Context) -> None:
    changelog_filename = "CHANGELOG.md"
    click.secho(f"> Updating {changelog_filename}.", fg="cyan")

    if not os.path.exists(changelog_filename):
        click.secho(
            f"{changelog_filename} does not yet exist. Opening it for " "creation."
        )

        releasetool.filehelpers.open_editor_with_content(
            changelog_filename,
            _CHANGELOG_TEMPLATE.format(package_name=ctx.package_name),
        )

    if releasetool.filehelpers.detect(
        changelog_filename, f"### ({ctx.release_version})"
    ):
        click.secho(
            f"Version {ctx.release_version} already exists in {changelog_filename}. Aborting.",
            fg="magenta",
        )
        os.abort()

    changelog_entry = (
        f"### {ctx.release_version} / {ctx.today}"
        f"\n\n"
        f"{ctx.release_notes}"
        f"\n\n"
    )
    releasetool.filehelpers.insert_before(
        changelog_filename, changelog_entry, "^### (.+)$|\Z"
    )


def update_version(ctx: Context) -> None:
    version_rb = glob.glob("lib/**/version.rb", recursive=True)
    if version_rb:
        ctx.version_file = glob.glob("lib/**/version.rb", recursive=True)[0]
        releasetool.filehelpers.replace(
            ctx.version_file, r'VERSION = "(.+?)"', f'VERSION = "{ctx.release_version}"'
        )
    else:
        ctx.version_file = f"{ctx.package_name}.gemspec"
        releasetool.filehelpers.replace(
            ctx.version_file,
            r'gem.version(\s+)= "(.+?)"',
            # TODO: Use regex group above to fill # of spaces before the = sign.
            f'gem.version       = "{ctx.release_version}"',
        )

    click.secho(f"> Updating {ctx.version_file} to {ctx.release_version}", fg="cyan")


def create_release_commit(ctx: Context) -> None:
    """Create a release commit."""
    click.secho("> Committing changes to CHANGELOG.md, {ctx.version_file}", fg="cyan")
    releasetool.git.commit(
        ["CHANGELOG.md", ctx.version_file],
        f"Release {ctx.package_name} {ctx.release_version}\n\n{ctx.release_notes}",
    )


def push_release_branch(ctx: Context) -> None:
    click.secho("> Pushing release branch.", fg="cyan")
    releasetool.git.push(ctx.release_branch)


def create_release_pr(ctx: Context) -> None:
    click.secho("> Creating release pull request.", fg="cyan")

    if ctx.upstream_repo == ctx.origin_repo:
        head = ctx.release_branch
    else:
        head = f"{ctx.origin_user}:{ctx.release_branch}"

    pr_changes = releasetool.git.summary_log(
        from_=f"{ctx.upstream_name}/master", to="HEAD", where="..", format="%s%n%n%b"
    )

    ctx.pull_request = ctx.github.create_pull_request(
        ctx.upstream_repo,
        head=head,
        title=f"Releases {ctx.today}",
        body="\n".join(pr_changes),
    )
    click.secho(f"Pull request is at {ctx.pull_request['html_url']}.")


def start() -> None:
    ctx = Context()

    click.secho(f"o/ Hey, {getpass.getuser()}, let's release some Ruby!", fg="magenta")

    releasetool.commands.common.setup_github_context(ctx)
    create_release_branch(ctx)
    determine_package_name(ctx)
    determine_last_release(ctx)
    gather_changes(ctx)
    edit_release_notes(ctx)
    determine_release_version(ctx)
    update_changelog(ctx)
    update_version(ctx)
    create_release_commit(ctx)
    if click.confirm("Are you ready to create your release PR?"):
        # TODO: Rebase on master?
        push_release_branch(ctx)
        # TODO: Confirm?
        create_release_pr(ctx)

    click.secho("\o/ All done!", fg="magenta")
