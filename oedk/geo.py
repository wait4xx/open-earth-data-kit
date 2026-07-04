"""地理空间子集裁剪共享工具。

OPeNDAP 和 Icechunk 两个导出型 adapter 都需要按经纬度边界框裁剪 xarray
数据集，且面临完全相同的问题 (lon/longitude、lat/latitude 坐标名不一致，
纬度可能递减排列)，逻辑也完全相同，故抽到这里共用，避免重复维护。
"""

from __future__ import annotations


def subset_region(ds, region):
    """按经纬度边界框裁剪 xarray 数据集，自动适配坐标名和纬度方向。

    ``region`` 为 ``None`` 时原样返回 ``ds``；否则应为
    ``(lon_min, lon_max, lat_min, lat_max)``。纬度递减排列时 slice 参数
    自动反向，避免切到空集。
    """
    if not region:
        return ds
    lon_min, lon_max, lat_min, lat_max = region
    lon_name = "lon" if "lon" in ds.coords else "longitude" if "longitude" in ds.coords else None
    lat_name = "lat" if "lat" in ds.coords else "latitude" if "latitude" in ds.coords else None
    if lon_name:
        ds = ds.sel({lon_name: slice(lon_min, lon_max)})
    if lat_name:
        values = ds[lat_name].values
        if len(values) >= 2 and values[0] > values[-1]:
            # 纬度递减排列 (常见)，slice 参数要反向。
            ds = ds.sel({lat_name: slice(lat_max, lat_min)})
        else:
            ds = ds.sel({lat_name: slice(lat_min, lat_max)})
    return ds
