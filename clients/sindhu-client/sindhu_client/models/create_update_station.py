from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_update_station_metadata_type_0 import CreateUpdateStationMetadataType0
    from ..models.geo_object import GeoObject


T = TypeVar("T", bound="CreateUpdateStation")


@_attrs_define
class CreateUpdateStation:
    """
    Attributes:
        name (str):
        name_th (None | str):
        code (str):
        source (str):
        url (str):
        coordinates (GeoObject):
        metadata (CreateUpdateStationMetadataType0 | None | Unset):
        status (str | Unset):  Default: 'active'.
    """

    name: str
    name_th: None | str
    code: str
    source: str
    url: str
    coordinates: GeoObject
    metadata: CreateUpdateStationMetadataType0 | None | Unset = UNSET
    status: str | Unset = "active"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.create_update_station_metadata_type_0 import CreateUpdateStationMetadataType0

        name = self.name

        name_th: None | str
        name_th = self.name_th

        code = self.code

        source = self.source

        url = self.url

        coordinates = self.coordinates.to_dict()

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, CreateUpdateStationMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        status = self.status

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
            }
        )
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_update_station_metadata_type_0 import CreateUpdateStationMetadataType0
        from ..models.geo_object import GeoObject

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

        def _parse_metadata(data: object) -> CreateUpdateStationMetadataType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = CreateUpdateStationMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CreateUpdateStationMetadataType0 | None | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        status = d.pop("status", UNSET)

        create_update_station = cls(
            name=name,
            name_th=name_th,
            code=code,
            source=source,
            url=url,
            coordinates=coordinates,
            metadata=metadata,
            status=status,
        )

        create_update_station.additional_properties = d
        return create_update_station

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
