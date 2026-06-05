from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.db_settings.init_indexes import init_indexes


if __name__ == "__main__":
    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    init_indexes()