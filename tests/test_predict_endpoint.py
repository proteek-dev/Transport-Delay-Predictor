from __future__ import annotations

from httpx import AsyncClient


async def test_openapi_advertises_predict_and_live_delays(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/predict" in paths
    predict_op = paths["/predict"]["get"]
    param_names = {p["name"] for p in predict_op["parameters"]}
    # Per spec: GET /predict?route_id=X&stop_id=Y&datetime=Z
    assert {"route_id", "stop_id", "datetime"}.issubset(param_names)

    assert "/delays/live" in paths
    live_op = paths["/delays/live"]["get"]
    live_params = {p["name"] for p in live_op["parameters"]}
    # Optional filters — route_id and stop_id must be query params, not required.
    assert {"route_id", "stop_id"}.issubset(live_params)


async def test_predict_response_schema_shape(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    schema = response.json()
    predict_response_ref = (
        schema["paths"]["/predict"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    )
    # FastAPI emits a $ref for the response model; resolve to confirm the field shape.
    ref = predict_response_ref["$ref"].split("/")[-1]
    component = schema["components"]["schemas"][ref]
    required_fields = set(component.get("required", []))
    assert {
        "route_id",
        "stop_id",
        "datetime",
        "predicted_delay_seconds",
        "method",
        "sample_size",
        "confidence",
    }.issubset(required_fields)
    # confidence_interval must be nullable on the schema.
    assert "confidence_interval" in component["properties"]
