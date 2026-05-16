from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.body_all_v1_stations_get import BodyAllV1StationsGet
from ...models.http_validation_error import HTTPValidationError
from ...models.station_list import StationList
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: BodyAllV1StationsGet | Unset = UNSET,
    status: str | Unset = "active",
    name: None | str | Unset = UNSET,
    name_th: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["status"] = status

    json_name: None | str | Unset
    if isinstance(name, Unset):
        json_name = UNSET
    else:
        json_name = name
    params["name"] = json_name

    json_name_th: None | str | Unset
    if isinstance(name_th, Unset):
        json_name_th = UNSET
    else:
        json_name_th = name_th
    params["name_th"] = json_name_th

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/stations",
        "params": params,
    }

    if not isinstance(body, Unset):
        _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: BodyAllV1StationsGet | Unset = UNSET,
    status: str | Unset = "active",
    name: None | str | Unset = UNSET,
    name_th: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | StationList]:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        name (None | str | Unset):
        name_th (None | str | Unset):
        body (BodyAllV1StationsGet | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StationList]
    """

    kwargs = _get_kwargs(
        body=body,
        status=status,
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
    body: BodyAllV1StationsGet | Unset = UNSET,
    status: str | Unset = "active",
    name: None | str | Unset = UNSET,
    name_th: None | str | Unset = UNSET,
) -> HTTPValidationError | StationList | None:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        name (None | str | Unset):
        name_th (None | str | Unset):
        body (BodyAllV1StationsGet | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StationList
    """

    return sync_detailed(
        client=client,
        body=body,
        status=status,
        name=name,
        name_th=name_th,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAllV1StationsGet | Unset = UNSET,
    status: str | Unset = "active",
    name: None | str | Unset = UNSET,
    name_th: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | StationList]:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        name (None | str | Unset):
        name_th (None | str | Unset):
        body (BodyAllV1StationsGet | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StationList]
    """

    kwargs = _get_kwargs(
        body=body,
        status=status,
        name=name,
        name_th=name_th,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAllV1StationsGet | Unset = UNSET,
    status: str | Unset = "active",
    name: None | str | Unset = UNSET,
    name_th: None | str | Unset = UNSET,
) -> HTTPValidationError | StationList | None:
    """All

    Args:
        status (str | Unset):  Default: 'active'.
        name (None | str | Unset):
        name_th (None | str | Unset):
        body (BodyAllV1StationsGet | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StationList
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            status=status,
            name=name,
            name_th=name_th,
        )
    ).parsed
