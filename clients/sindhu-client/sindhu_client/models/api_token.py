from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ApiToken")


@_attrs_define
class ApiToken:
    """
    Attributes:
        created_date (datetime.datetime):
        updated_date (datetime.datetime):
        source (None | str | Unset):  Default: ''.
        access_token (None | str | Unset):  Default: ''.
        access_token_expires (datetime.datetime | None | Unset):
        refresh_token (None | str | Unset):  Default: ''.
        refresh_token_expires (datetime.datetime | None | Unset):
        id (str | Unset):  Example: 5eb7cf5a86d9755df3a6c593.
    """

    created_date: datetime.datetime
    updated_date: datetime.datetime
    source: None | str | Unset = ""
    access_token: None | str | Unset = ""
    access_token_expires: datetime.datetime | None | Unset = UNSET
    refresh_token: None | str | Unset = ""
    refresh_token_expires: datetime.datetime | None | Unset = UNSET
    id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_date = self.created_date.isoformat()

        updated_date = self.updated_date.isoformat()

        source: None | str | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        else:
            source = self.source

        access_token: None | str | Unset
        if isinstance(self.access_token, Unset):
            access_token = UNSET
        else:
            access_token = self.access_token

        access_token_expires: None | str | Unset
        if isinstance(self.access_token_expires, Unset):
            access_token_expires = UNSET
        elif isinstance(self.access_token_expires, datetime.datetime):
            access_token_expires = self.access_token_expires.isoformat()
        else:
            access_token_expires = self.access_token_expires

        refresh_token: None | str | Unset
        if isinstance(self.refresh_token, Unset):
            refresh_token = UNSET
        else:
            refresh_token = self.refresh_token

        refresh_token_expires: None | str | Unset
        if isinstance(self.refresh_token_expires, Unset):
            refresh_token_expires = UNSET
        elif isinstance(self.refresh_token_expires, datetime.datetime):
            refresh_token_expires = self.refresh_token_expires.isoformat()
        else:
            refresh_token_expires = self.refresh_token_expires

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created_date": created_date,
                "updated_date": updated_date,
            }
        )
        if source is not UNSET:
            field_dict["source"] = source
        if access_token is not UNSET:
            field_dict["access_token"] = access_token
        if access_token_expires is not UNSET:
            field_dict["access_token_expires"] = access_token_expires
        if refresh_token is not UNSET:
            field_dict["refresh_token"] = refresh_token
        if refresh_token_expires is not UNSET:
            field_dict["refresh_token_expires"] = refresh_token_expires
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_date = isoparse(d.pop("created_date"))

        updated_date = isoparse(d.pop("updated_date"))

        def _parse_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

        def _parse_access_token(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        access_token = _parse_access_token(d.pop("access_token", UNSET))

        def _parse_access_token_expires(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                access_token_expires_type_0 = isoparse(data)

                return access_token_expires_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        access_token_expires = _parse_access_token_expires(d.pop("access_token_expires", UNSET))

        def _parse_refresh_token(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        refresh_token = _parse_refresh_token(d.pop("refresh_token", UNSET))

        def _parse_refresh_token_expires(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                refresh_token_expires_type_0 = isoparse(data)

                return refresh_token_expires_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        refresh_token_expires = _parse_refresh_token_expires(d.pop("refresh_token_expires", UNSET))

        id = d.pop("id", UNSET)

        api_token = cls(
            created_date=created_date,
            updated_date=updated_date,
            source=source,
            access_token=access_token,
            access_token_expires=access_token_expires,
            refresh_token=refresh_token,
            refresh_token_expires=refresh_token_expires,
            id=id,
        )

        api_token.additional_properties = d
        return api_token

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
