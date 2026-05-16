from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.station import Station


T = TypeVar("T", bound="StationList")


@_attrs_define
class StationList:
    """
    Attributes:
        stations (list[Station]):
    """

    stations: list[Station]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        stations = []
        for stations_item_data in self.stations:
            stations_item = stations_item_data.to_dict()
            stations.append(stations_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "stations": stations,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.station import Station

        d = dict(src_dict)
        stations = []
        _stations = d.pop("stations")
        for stations_item_data in _stations:
            stations_item = Station.from_dict(stations_item_data)

            stations.append(stations_item)

        station_list = cls(
            stations=stations,
        )

        station_list.additional_properties = d
        return station_list

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
