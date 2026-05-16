from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.geo_object import GeoObject


T = TypeVar("T", bound="CreateSystemSetting")


@_attrs_define
class CreateSystemSetting:
    """
    Attributes:
        center (GeoObject | None | Unset):
        interpolation_coordinate_1 (GeoObject | None | Unset):
        interpolation_coordinate_2 (GeoObject | None | Unset):
        zoom (int | None | Unset):
        min_zoom (int | None | Unset):
    """

    center: GeoObject | None | Unset = UNSET
    interpolation_coordinate_1: GeoObject | None | Unset = UNSET
    interpolation_coordinate_2: GeoObject | None | Unset = UNSET
    zoom: int | None | Unset = UNSET
    min_zoom: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.geo_object import GeoObject

        center: dict[str, Any] | None | Unset
        if isinstance(self.center, Unset):
            center = UNSET
        elif isinstance(self.center, GeoObject):
            center = self.center.to_dict()
        else:
            center = self.center

        interpolation_coordinate_1: dict[str, Any] | None | Unset
        if isinstance(self.interpolation_coordinate_1, Unset):
            interpolation_coordinate_1 = UNSET
        elif isinstance(self.interpolation_coordinate_1, GeoObject):
            interpolation_coordinate_1 = self.interpolation_coordinate_1.to_dict()
        else:
            interpolation_coordinate_1 = self.interpolation_coordinate_1

        interpolation_coordinate_2: dict[str, Any] | None | Unset
        if isinstance(self.interpolation_coordinate_2, Unset):
            interpolation_coordinate_2 = UNSET
        elif isinstance(self.interpolation_coordinate_2, GeoObject):
            interpolation_coordinate_2 = self.interpolation_coordinate_2.to_dict()
        else:
            interpolation_coordinate_2 = self.interpolation_coordinate_2

        zoom: int | None | Unset
        if isinstance(self.zoom, Unset):
            zoom = UNSET
        else:
            zoom = self.zoom

        min_zoom: int | None | Unset
        if isinstance(self.min_zoom, Unset):
            min_zoom = UNSET
        else:
            min_zoom = self.min_zoom

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if center is not UNSET:
            field_dict["center"] = center
        if interpolation_coordinate_1 is not UNSET:
            field_dict["interpolation_coordinate_1"] = interpolation_coordinate_1
        if interpolation_coordinate_2 is not UNSET:
            field_dict["interpolation_coordinate_2"] = interpolation_coordinate_2
        if zoom is not UNSET:
            field_dict["zoom"] = zoom
        if min_zoom is not UNSET:
            field_dict["min_zoom"] = min_zoom

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.geo_object import GeoObject

        d = dict(src_dict)

        def _parse_center(data: object) -> GeoObject | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                center_type_0 = GeoObject.from_dict(data)

                return center_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GeoObject | None | Unset, data)

        center = _parse_center(d.pop("center", UNSET))

        def _parse_interpolation_coordinate_1(data: object) -> GeoObject | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                interpolation_coordinate_1_type_0 = GeoObject.from_dict(data)

                return interpolation_coordinate_1_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GeoObject | None | Unset, data)

        interpolation_coordinate_1 = _parse_interpolation_coordinate_1(d.pop("interpolation_coordinate_1", UNSET))

        def _parse_interpolation_coordinate_2(data: object) -> GeoObject | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                interpolation_coordinate_2_type_0 = GeoObject.from_dict(data)

                return interpolation_coordinate_2_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(GeoObject | None | Unset, data)

        interpolation_coordinate_2 = _parse_interpolation_coordinate_2(d.pop("interpolation_coordinate_2", UNSET))

        def _parse_zoom(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        zoom = _parse_zoom(d.pop("zoom", UNSET))

        def _parse_min_zoom(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_zoom = _parse_min_zoom(d.pop("min_zoom", UNSET))

        create_system_setting = cls(
            center=center,
            interpolation_coordinate_1=interpolation_coordinate_1,
            interpolation_coordinate_2=interpolation_coordinate_2,
            zoom=zoom,
            min_zoom=min_zoom,
        )

        create_system_setting.additional_properties = d
        return create_system_setting

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
