from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.station_list import StationList
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: str | Unset = "active",
    source: list[str] | Unset = UNSET,
    station_code: list[str] | Unset = UNSET,
    name: str | Unset = UNSET,
    name_th: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["status"] = status

    json_source: list[str] | Unset = UNSET
    if not isinstance(source, Unset):
        json_source = source

    params["source"] = json_source

    json_station_code: list[str] | Unset = UNSET
    if not isinstance(station_code, Unset):
        json_station_code = station_code

    params["station_code"] = json_station_code

    params["name"] = name

    params["name_th"] = name_th

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/stations",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StationList | None:
    if response.status_code == 200:
        response_200 = StationList.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | StationList]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = "active",
    source: list[str] | Unset = UNSET,
    station_code: list[str] | Unset = UNSET,
    name: str | Unset = UNSET,
    name_th: str | Unset = UNSET,
) -> Response[HTTPValidationError | StationList]:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        source (list[str] | Unset):
        station_code (list[str] | Unset):
        name (str | Unset):
        name_th (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StationList]
    """

    kwargs = _get_kwargs(
        status=status,
        source=source,
        station_code=station_code,
        name=name,
        name_th=name_th,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = "active",
    source: list[str] | Unset = UNSET,
    station_code: list[str] | Unset = UNSET,
    name: str | Unset = UNSET,
    name_th: str | Unset = UNSET,
) -> HTTPValidationError | StationList | None:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        source (list[str] | Unset):
        station_code (list[str] | Unset):
        name (str | Unset):
        name_th (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StationList
    """

    return sync_detailed(
        client=client,
        status=status,
        source=source,
        station_code=station_code,
        name=name,
        name_th=name_th,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = "active",
    source: list[str] | Unset = UNSET,
    station_code: list[str] | Unset = UNSET,
    name: str | Unset = UNSET,
    name_th: str | Unset = UNSET,
) -> Response[HTTPValidationError | StationList]:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        source (list[str] | Unset):
        station_code (list[str] | Unset):
        name (str | Unset):
        name_th (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StationList]
    """

    kwargs = _get_kwargs(
        status=status,
        source=source,
        station_code=station_code,
        name=name,
        name_th=name_th,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = "active",
    source: list[str] | Unset = UNSET,
    station_code: list[str] | Unset = UNSET,
    name: str | Unset = UNSET,
    name_th: str | Unset = UNSET,
) -> HTTPValidationError | StationList | None:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        source (list[str] | Unset):
        station_code (list[str] | Unset):
        name (str | Unset):
        name_th (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StationList
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
            source=source,
            station_code=station_code,
            name=name,
            name_th=name_th,
        )
    ).parsed
