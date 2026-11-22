from tests.api.conftest import ApiTestContext


async def test_tools_returns_input_and_output_json_schema(
    api_context: ApiTestContext,
) -> None:
    response = await api_context.client.get("/api/v1/tools")

    assert response.status_code == 200
    tools = {item["name"]: item for item in response.json()["items"]}
    assert tools["wait_for_host"]["execution_mode"] == "remote"
    assert tools["wait_for_host"]["input_schema"]["type"] == "object"
    assert tools["echo"]["execution_mode"] == "local"
    assert tools["echo"]["output_schema"]["type"] == "object"
