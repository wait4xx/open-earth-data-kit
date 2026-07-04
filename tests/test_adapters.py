"""Adapter 注册表与 Protocol 枚举一致性测试。"""

from oedk.adapters import adapter_for
from oedk.adapters.base import _ADAPTER_REGISTRY
from oedk.models import Protocol


def test_protocol_enum_matches_adapter_registry():
    """Protocol 枚举值必须与 adapter 注册表键完全一致。

    新增 adapter 时需同时改 Protocol 枚举 (models.py) 和注册表
    (adapters/base.py)；本测试在两者失同步时立即失败。
    """
    protocol_values = {p.value for p in Protocol}
    registry_keys = set(_ADAPTER_REGISTRY)

    assert protocol_values == registry_keys


def test_adapter_for_returns_instance_for_each_protocol():
    """每个 Protocol 值都能通过 adapter_for 拿到 Adapter 实例。"""
    for p in Protocol:
        adapter = adapter_for(p.value)
        assert adapter is not None


def test_adapter_for_unknown_name_raises_key_error():
    """未注册的名字应抛 KeyError。"""
    import pytest

    with pytest.raises(KeyError):
        adapter_for("nonexistent_adapter")
