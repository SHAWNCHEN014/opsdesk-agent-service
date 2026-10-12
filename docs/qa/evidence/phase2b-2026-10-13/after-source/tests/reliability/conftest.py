import json

import pytest


@pytest.fixture
def record(request):
    """Keep synthetic state observations in JUnit, including on a red run."""
    def save(value):
        request.node.user_properties.append(("reliability_evidence", json.dumps(value, ensure_ascii=False)))
    return save
