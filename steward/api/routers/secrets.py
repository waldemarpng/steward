"""Granted secrets as env, JSON, and YAML."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response

from steward.api.dependencies import available
from steward.api.formats import to_env, to_json, to_yaml

router = APIRouter(tags=["secrets"])


@router.get("/secrets.env", response_class=PlainTextResponse)
async def secrets_env(values: Annotated[dict[str, str], Depends(available)]) -> PlainTextResponse:
    """Granted secrets as KEY=value text. 401 when the bearer token cannot be used."""
    return PlainTextResponse(to_env(values))


@router.get("/secrets.json")
async def secrets_json(values: Annotated[dict[str, str], Depends(available)]) -> Response:
    """Granted secrets as a JSON object. 401 when the bearer token cannot be used."""
    return Response(to_json(values), media_type="application/json")


@router.get("/secrets.yaml", response_class=PlainTextResponse)
async def secrets_yaml(values: Annotated[dict[str, str], Depends(available)]) -> PlainTextResponse:
    """Granted secrets as a YAML mapping. 401 when the bearer token cannot be used."""
    return PlainTextResponse(to_yaml(values), media_type="application/yaml")
