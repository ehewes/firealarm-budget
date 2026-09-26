from uuid import uuid4

import pytest
from pydantic import ValidationError

from eden_core.codes import is_session_code, new_session_code
from eden_core.jobs import ClassifyJob, PageJob, parse_job
from eden_core.reachable import _private


def test_session_codes_have_the_0001_shape():
    codes = {new_session_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(is_session_code(code) for code in codes)
    assert not is_session_code("EM-0000000O")
    assert not is_session_code("em-7k2q9x4m")


def test_jobs_round_trip():
    scrape_id = uuid4()
    page = parse_job({"v": 1, "kind": "page", "scrape_id": str(scrape_id), "url": "https://a.io/"})
    assert isinstance(page, PageJob) and page.scrape_id == scrape_id and page.depth == 0
    classify = parse_job({"v": 1, "kind": "classify", "session_id": str(uuid4())})
    assert isinstance(classify, ClassifyJob)
    with pytest.raises(ValidationError):
        parse_job({"v": 2, "kind": "page"})


@pytest.mark.parametrize(
    ("address", "private"),
    [
        ("8.8.8.8", False),
        ("2606:4700::1111", False),
        ("10.1.2.3", True),
        ("127.0.0.1", True),
        ("169.254.169.254", True),
        ("100.102.111.88", True),  # the tailnet
        ("::ffff:192.168.1.1", True),
    ],
)
def test_private_addresses(address, private):
    assert _private(address) is private
