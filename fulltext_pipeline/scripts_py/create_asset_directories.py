from ai4research.fulltext_pipeline.config import ensure_asset_directories


def main() -> None:
    ensure_asset_directories()
    print("✅ 全文资产目录创建完成")


if __name__ == "__main__":
    main()

# python -m ai4research.fulltext_pipeline.scripts_py.create_asset_directories