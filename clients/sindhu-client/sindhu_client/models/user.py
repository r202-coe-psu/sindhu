from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="User")


@_attrs_define
class User:
    """
    Attributes:
        email (str):  Example: admin@email.local.
        username (str):  Example: admin.
        first_name (str):  Example: Firstname.
        last_name (str):  Example: Lastname.
        status (str):  Example: active.
        roles (list[str]):
        id (str | Unset):  Example: 5eb7cf5a86d9755df3a6c593.
        last_login_date (datetime.datetime | None | Unset):  Example: 2023-01-01T00:00:00.000000.
    """

    email: str
    username: str
    first_name: str
    last_name: str
    status: str
    roles: list[str]
    id: str | Unset = UNSET
    last_login_date: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        username = self.username

        first_name = self.first_name

        last_name = self.last_name

        status = self.status

        roles = self.roles

        id = self.id

        last_login_date: None | str | Unset
        if isinstance(self.last_login_date, Unset):
            last_login_date = UNSET
        elif isinstance(self.last_login_date, datetime.datetime):
            last_login_date = self.last_login_date.isoformat()
        else:
            last_login_date = self.last_login_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "email": email,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "status": status,
                "roles": roles,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if last_login_date is not UNSET:
            field_dict["last_login_date"] = last_login_date

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        username = d.pop("username")

        first_name = d.pop("first_name")

        last_name = d.pop("last_name")

        status = d.pop("status")

        roles = cast(list[str], d.pop("roles"))

        id = d.pop("id", UNSET)

        def _parse_last_login_date(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_login_date_type_0 = isoparse(data)

                return last_login_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        last_login_date = _parse_last_login_date(d.pop("last_login_date", UNSET))

        user = cls(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            status=status,
            roles=roles,
            id=id,
            last_login_date=last_login_date,
        )

        user.additional_properties = d
        return user

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
