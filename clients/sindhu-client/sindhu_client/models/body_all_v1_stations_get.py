from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BodyAllV1StationsGet")


@_attrs_define
class BodyAllV1StationsGet:
    """
    Attributes:
        source (list[str] | None | Unset):
        station_code (list[str] | None | Unset):
    """

    source: list[str] | None | Unset = UNSET
    station_code: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source: list[str] | None | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        elif isinstance(self.source, list):
            source = self.source

        else:
            source = self.source

        station_code: list[str] | None | Unset
        if isinstance(self.station_code, Unset):
            station_code = UNSET
        elif isinstance(self.station_code, list):
            station_code = self.station_code

        else:
            station_code = self.station_code

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if source is not UNSET:
            field_dict["source"] = source
        if station_code is not UNSET:
            field_dict["station_code"] = station_code

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_source(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                source_type_0 = cast(list[str], data)

                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        source = _parse_source(d.pop("source", UNSET))

        def _parse_station_code(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                station_code_type_0 = cast(list[str], data)

                return station_code_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        station_code = _parse_station_code(d.pop("station_code", UNSET))

        body_all_v1_stations_get = cls(
            source=source,
            station_code=station_code,
        )

        body_all_v1_stations_get.additional_properties = d
        return body_all_v1_stations_get

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
