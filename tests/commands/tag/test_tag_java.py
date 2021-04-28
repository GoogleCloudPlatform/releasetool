# Copyright 2019 Google LLC
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

from releasetool.commands.tag.java import (
    _parse_release_tag,
    kokoro_job_name,
    package_name,
)

RELEASE_PLEASE_OUTPUT = """
✔ creating release v1.20.0
✔ Created release: https://github.com/googleapis/java-bigtable/releases/tag/v1.20.0.
✔ adding comment to https://github.com/googleapis/java-bigtable/issue/610
✔ adding label autorelease: tagged to https://github.com/googleapis/java-bigtable/pull/610
✔ removing label autorelease: pending from 610
"""


def test_releasetool_release_tag():
    expected = "v1.20.0"
    assert _parse_release_tag(RELEASE_PLEASE_OUTPUT) == expected


def test_kokoro_job_name():
    job_name = kokoro_job_name("upstream-owner/upstream-repo", "some-package-name")
    assert job_name == "cloud-devrel/client-libraries/java/upstream-repo/release/stage"


def test_package_name():
    name = package_name({"head": {"ref": "release-storage-v1.2.3"}})
    assert name is None
