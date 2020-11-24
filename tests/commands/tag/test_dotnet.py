# Copyright 2020, Google LLC
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

import pytest
import re

from releasetool.commands.tag.dotnet import RELEASE_LINE_PATTERN


release_triggering_lines = [
    ("Release Google.LongRunning version 1.2.3", "Google.LongRunning", "1.2.3"),
    (
        "Release Google.LongRunning version 1.2.3-beta01",
        "Google.LongRunning",
        "1.2.3-beta01",
    ),
    ("- Release Google.LongRunning version 1.2.3", "Google.LongRunning", "1.2.3"),
]

non_release_triggering_lines = [
    ("Release new version of all OsLogin packages"),
    ("Release all OsLogin packages version 1.2.3"),
    ("Release Google.LongRunning version 1.0"),
    ("Release Google.LongRunning version 1.2.3 and 1.2.4"),
]


@pytest.mark.parametrize("line,package,version", release_triggering_lines)
def test_release_line_regex_matching(line, package, version):
    """
    The regex can extract a well-formatted package and version
    """
    match = re.search(RELEASE_LINE_PATTERN, line)
    assert match is not None
    assert match.group(1) == package
    assert match.group(2) == version


@pytest.mark.parametrize("line", non_release_triggering_lines)
def test_release_line_regex_not_matching(line):
    """
    The regex is strict enough not to match other lines.
    """
    match = re.search(RELEASE_LINE_PATTERN, line)
    assert match is None
