"""Unit tests for the HTML injector."""

from harness.server.injector import inject_harness_vars


def test_injects_into_head():
    html = "<html><head><title>Test</title></head><body></body></html>"
    result = inject_harness_vars(
        html=html,
        component_id="comp_abc",
        api_base="http://localhost:8000",
        ws_base="ws://localhost:8000",
        initial_state={"count": 0},
        permissions=["ui.resize"],
    )
    assert "window.__HARNESS__" in result
    assert '"COMPONENT_ID": "comp_abc"' in result
    assert '"API_URL": "http://localhost:8000/api/comp_abc"' in result
    assert '"WS_URL": "ws://localhost:8000/ws/comp_abc"' in result
    # Script should be inside <head>
    head_end = result.index("</head>")
    script_pos = result.index("window.__HARNESS__")
    assert script_pos < head_end


def test_injects_without_head():
    html = "<html><body>No head</body></html>"
    result = inject_harness_vars(
        html=html,
        component_id="comp_xyz",
        api_base="http://localhost:8000",
        ws_base="ws://localhost:8000",
        initial_state={},
        permissions=[],
    )
    assert "window.__HARNESS__" in result
