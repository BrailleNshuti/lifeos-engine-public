import datetime as dt
from lifeos.tasks import list_tasks, new_task, read_frontmatter, slugify


def test_slugify():
    assert slugify("Rename the repos and write a profile README") == "rename-repos-write-profile"
    assert slugify("!!!") == "task"


def test_new_task_never_overwrites(tmp_path):
    day = dt.date(2026, 11, 16)
    first = new_task(tmp_path, "Write the profile README.", today=day)
    second = new_task(tmp_path, "Write the profile README", today=day)
    assert first.name == "T-261116-write-profile-readme.md"
    assert second.name == "T-261116-write-profile-readme-2.md"
    fields = read_frontmatter(second)
    assert fields["id"] == second.stem and fields["status"] == "inbox"
    assert fields["goal"] == "Write the profile README" and fields["done_when"].startswith("TODO")


def test_list_tasks_filters_by_status(demo, tmp_path):
    assert [t["id"] for t in list_tasks(demo, "doing")] == ["T-261116-demo-cli"]
    assert list_tasks(demo, "done") == []
