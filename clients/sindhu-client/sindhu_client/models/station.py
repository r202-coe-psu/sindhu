from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.geo_object import GeoObject
    from ..models.station_metadata_type_0 import StationMetadataType0


T = TypeVar("T", bound="Station")


@_attrs_define
class Station:
    """
    Attributes:
        name (str):
        name_th (None | str):
        code (str):
        source (str):
        url (str):
        coordinates (GeoObject):
        status (str):
        created_date (datetime.datetime):
        updated_date (datetime.datetime):
        metadata (None | StationMetadataType0 | Unset):
        id (str | Unset):  Example: 5eb7cf5a86d9755df3a6c593.
    """

    name: str
    name_th: None | str
    code: str
    source: str
    url: str
    coordinates: GeoObject
    status: str
    created_date: datetime.datetime
    updated_date: datetime.datetime
    metadata: None | StationMetadataType0 | Unset = UNSET
    id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.station_metadata_type_0 import StationMetadataType0

        name = self.name

        name_th: None | str
        name_th = self.name_th

        code = self.code

        source = self.source

        url = self.url

        coordinates = self.coordinates.to_dict()

        status = self.status

        created_date = self.created_date.isoformat()

        updated_date = self.updated_date.isoformat()

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, StationMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "name_th": name_th,
                "code": code,
                "source": source,
                "url": url,
                "coordinates": coordinates,
                "status": status,
                "created_date": created_date,
                "updated_date": updated_date,
            }
        )
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.geo_object import GeoObject
        from ..models.station_metadata_type_0 import StationMetadataType0

        d = dict(src_dict)
        name = d.pop("name")

        def _parse_name_th(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        name_th = _parse_name_th(d.pop("name_th"))

        code = d.pop("code")

        source = d.pop("source")

        url = d.pop("url")

        coordinates = GeoObject.from_dict(d.pop("coordinates"))

        status = d.pop("status")

        created_date = isoparse(d.pop("created_date"))

        updated_date = isoparse(d.pop("updated_date"))

        def _parse_metadata(data: object) -> None | StationMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = StationMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | StationMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        id = d.pop("id", UNSET)

        station = cls(
            name=name,
            name_th=name_th,
            code=code,
            source=source,
            url=url,
            coordinates=coordinates,
            status=status,
            created_date=created_date,
            updated_date=updated_date,
            metadata=metadata,
            id=id,
        )

        station.additional_properties = d
        return station

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
