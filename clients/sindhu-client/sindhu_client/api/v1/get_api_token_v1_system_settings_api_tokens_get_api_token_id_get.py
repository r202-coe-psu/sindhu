from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.api_token_response import ApiTokenResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    api_token_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/system_settings/api_tokens/get/{api_token_id}".format(
            api_token_id=quote(str(api_token_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApiTokenResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApiTokenResponse.from_dict(response.json())

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
) -> Response[ApiTokenResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    api_token_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[ApiTokenResponse | HTTPValidationError]:
    """Get Api Token

    Args:
        api_token_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiTokenResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        api_token_id=api_token_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    api_token_id: str,
    *,
    client: AuthenticatedClient,
) -> ApiTokenResponse | HTTPValidationError | None:
    """Get Api Token

    Args:
        api_token_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiTokenResponse | HTTPValidationError
    """

    return sync_detailed(
        api_token_id=api_token_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    api_token_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[ApiTokenResponse | HTTPValidationError]:
    """Get Api Token

    Args:
        api_token_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApiTokenResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        api_token_id=api_token_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    api_token_id: str,
    *,
    client: AuthenticatedClient,
) -> ApiTokenResponse | HTTPValidationError | None:
    """Get Api Token

    Args:
        api_token_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApiTokenResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            api_token_id=api_token_id,
            client=client,
        )
    ).parsed
