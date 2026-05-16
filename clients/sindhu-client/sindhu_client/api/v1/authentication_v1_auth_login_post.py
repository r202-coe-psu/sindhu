from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.body_authentication_v1_auth_login_post import BodyAuthenticationV1AuthLoginPost
from ...models.http_validation_error import HTTPValidationError
from ...models.token import Token
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: BodyAuthenticationV1AuthLoginPost,
    name: Any | Unset = "auth:login",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["name"] = name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/auth/login",
        "params": params,
    }

    _kwargs["data"] = body.to_dict()

    headers["Content-Type"] = "application/x-www-form-urlencoded"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | Token | None:
    if response.status_code == 200:
        response_200 = Token.from_dict(response.json())

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
) -> Response[HTTPValidationError | Token]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAuthenticationV1AuthLoginPost,
    name: Any | Unset = "auth:login",
) -> Response[HTTPValidationError | Token]:
    """Authentication

    Args:
        name (Any | Unset):  Default: 'auth:login'.
        body (BodyAuthenticationV1AuthLoginPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Token]
    """

    kwargs = _get_kwargs(
        body=body,
        name=name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAuthenticationV1AuthLoginPost,
    name: Any | Unset = "auth:login",
) -> HTTPValidationError | Token | None:
    """Authentication

    Args:
        name (Any | Unset):  Default: 'auth:login'.
        body (BodyAuthenticationV1AuthLoginPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Token
    """

    return sync_detailed(
        client=client,
        body=body,
        name=name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAuthenticationV1AuthLoginPost,
    name: Any | Unset = "auth:login",
) -> Response[HTTPValidationError | Token]:
    """Authentication

    Args:
        name (Any | Unset):  Default: 'auth:login'.
        body (BodyAuthenticationV1AuthLoginPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Token]
    """

    kwargs = _get_kwargs(
        body=body,
        name=name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: BodyAuthenticationV1AuthLoginPost,
    name: Any | Unset = "auth:login",
) -> HTTPValidationError | Token | None:
    """Authentication

    Args:
        name (Any | Unset):  Default: 'auth:login'.
        body (BodyAuthenticationV1AuthLoginPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Token
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            name=name,
        )
    ).parsed
