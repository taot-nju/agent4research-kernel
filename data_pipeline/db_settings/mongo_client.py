"""
描述：封装 MongoDB 连接，并提供一个单例方式获取 collection。

Returns:
    Collection: MongoDB collection 对象，可以直接用于数据库操作。
"""

from pymongo import MongoClient

from ai4research.data_pipeline.db_settings.mongo_config import (
    MONGO_URI,
    DB_NAME,
    COLLECTION_NAME,
)


class MongoDBClient:
    """
    描述：封装 MongoDB 连接。
    功能：
        1. 获取目标数据库中的 collection；
        2. 测试 MongoDB 是否连接正常。
    """
    _client = None
    _db = None
    _collection = None

    @classmethod
    def get_collection(cls):
        if cls._client is None:
            cls._client = MongoClient(MONGO_URI)
            cls._db = cls._client[DB_NAME]
            cls._collection = cls._db[COLLECTION_NAME]
        return cls._collection

    @classmethod
    def ping(cls):
        """
        测试 MongoDB 是否连接正常。
        如果 MongoDB 没启动、端口不对、URI 错误，这里会直接报错。
        """
        if cls._client is None:
            cls._client = MongoClient(MONGO_URI)
            cls._db = cls._client[DB_NAME]
            cls._collection = cls._db[COLLECTION_NAME]

        cls._client.admin.command("ping")
        return True
    


if __name__ == "__main__":
    print(MongoDBClient.ping())  # 如果连接成功，输出 True；如果连接失败，会抛出异常。


# 执行：
# cd ~
# python -m ai4research.data_pipeline.db_settings.mongo_client
# 输出：True（如果连接成功）或者报错（如果连接失败，例如 MongoDB 没启动、URI 错误、端口不对等）。