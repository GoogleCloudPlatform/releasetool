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

import datetime

import click
from dateutil import tz

import releasetool.commands.start.python
from releasetool.commands.start.python import Context


def determine_release_version(ctx: Context) -> None:
    ctx.release_version = (
        datetime.datetime.now(datetime.timezone.utc)
        .astimezone(tz.gettz("US/Pacific"))
        .strftime("%Y.%m.%d")
    )
    click.secho(f"Releasing {ctx.release_version}.")


# Python tools has different versioning, otherwise the process is the same as
# Python libraries.
releasetool.commands.start.python.determine_release_version = determine_release_version

start = releasetool.commands.start.python.start
