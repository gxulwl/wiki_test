import datetime
import os
import subprocess


def get_version(version=None):
    version = get_complete_version(version)
    major = get_major_version(version)

    sub = ""
    if version[3] == "alpha" and version[4] == 0:
        git_changeset = get_git_changeset()
        if git_changeset:
            sub = ".dev%s" % git_changeset

    elif version[3] != "final":
        mapping = {"alpha": "a", "beta": "b", "rc": "c"}
        sub = mapping[version[3]] + str(version[4])

    return str(major + sub)


def get_major_version(version=None):
    version = get_complete_version(version)
    parts = 2 if version[2] == 0 else 3
    major = ".".join(str(x) for x in version[:parts])
    return major


def get_complete_version(version=None):
    if version is None:
        from wiki_test import VERSION as version
    else:
        assert len(version) == 5
        assert version[3] in ("alpha", "beta", "rc", "final")

    return version


def get_docs_version(version=None):
    version = get_complete_version(version)
    if version[3] != "final":
        return "dev"
    else:
        return "%d.%d" % version[:2]


def get_git_changeset():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_log = subprocess.Popen(
        "git log --pretty=format:%ct --quiet -1 HEAD",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        cwd=repo_dir,
        universal_newlines=True,
    )
    timestamp = git_log.communicate()[0]
    try:
        timestamp = datetime.datetime.utcfromtimestamp(int(timestamp))
    except ValueError:
        return None
    return timestamp.strftime("%Y%m%d%H%M%S")
