# 贡献指南

**中文** | **[English](CONTRIBUTING_EN.md)**

本项目现在优先维护统一下载平台，而不是继续增加彼此独立的大脚本。贡献时请优先考虑：能否通过 catalog 配置解决；只有协议或认证流程无法复用时才新增适配器代码。

## 新增数据源

在 `catalog/sources.json` 中新增条目，至少包含：

```json
{
  "id": "provider_dataset",
  "name": "Readable dataset name",
  "category": "forecast",
  "provider": "Provider",
  "protocol": "http_index",
  "support_level": "downloadable",
  "endpoint": "https://example.com/data/",
  "formats": ["grib2"],
  "coverage": "time coverage",
  "defaults": {
    "file_extensions": [".grib2"],
    "max_files": 100
  }
}
```

字段要求：

- `id` 使用小写字母、数字和下划线，必须唯一。
- `support_level` 只能是 `downloadable`、`auth_required`、`manual`。
- 需要账号或 token 的来源必须写入 `required_credentials`。
- 不能把真实账号、token、cookie 或 session 写入 catalog。

## 新增适配器

只有以下情况才新增适配器：

- 现有 `http_index`、`s3_xml`、`opendap_xarray`、`icechunk_zarr`、`manual_auth` 无法表达该来源。
- 数据源需要特殊文件发现、分页、签名 URL、认证握手或导出逻辑。

适配器需要实现统一接口：

```python
class Adapter:
    def validate_config(self, request):
        return []

    def plan(self, request):
        ...
```

新增适配器后必须：

- 在 `oedk/adapters/base.py` 注册。
- 添加至少一个 catalog 示例。
- 添加单元测试。

## 测试

提交前运行：

```bash
conda activate oedk  # 或使用你当前的 conda 环境
python -m pytest
python -m oedk catalog validate
python -m oedk list --support downloadable
```

如果测试依赖网络，请改用 mock 响应，不要让单元测试依赖实时外部数据源。

## 文档

涉及用户行为的变更需要同步更新：

- `README.md`
- `README_EN.md`
- `CONTRIBUTING.md`
- `CONTRIBUTING_EN.md`

## 提交信息

推荐格式：

- `feat: add new data source catalog entry`
- `feat: add s3 pagination support`
- `fix: handle empty http index pages`
- `docs: update catalog contribution guide`
