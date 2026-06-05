"""
MongoDB的配置项，包括数据库URI、数据库名称和集合名称等。
这些配置项用于连接MongoDB数据库，并指定要操作的数据库和集合。
"""

# 本地数据库的地址
MONGO_URI = "mongodb://localhost:27017/"

# 目标数据库的名称
DB_NAME = "ai4research"

# 目标集合（表）的名称
COLLECTION_NAME = "papers"
