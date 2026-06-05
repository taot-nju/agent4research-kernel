from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.db_ops.paper_repository import migrate_schema


if __name__ == "__main__":
    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    migrate_schema()