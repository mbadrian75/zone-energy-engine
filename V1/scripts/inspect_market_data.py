from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DATABASE = "market_data"

COLLECTIONS = [
    "xauusd_d1",
    "xauusd_h4",
    "xauusd_h1",
    "xauusd_m30",
    "xauusd_m15",
    "xauusd_m5",
    "xauusd_m1",
]


def main():
    client = MongoClient(MONGO_URI)
    db = client[DATABASE]

    try:
        client.admin.command("ping")
        print("MongoDB connection: OK\n")

        for collection_name in COLLECTIONS:
            collection = db[collection_name]

            count = collection.count_documents({})

            first = collection.find_one(
                {},
                sort=[("datetime", 1)]
            )

            last = collection.find_one(
                {},
                sort=[("datetime", -1)]
            )

            print("=" * 60)
            print(f"Collection : {collection_name}")
            print(f"Documents  : {count:,}")

            if first:
                print(f"First      : {first['datetime']}")
                print(
                    f"First OHLC : "
                    f"O={first['open']} "
                    f"H={first['high']} "
                    f"L={first['low']} "
                    f"C={first['close']}"
                )

            if last:
                print(f"Last       : {last['datetime']}")
                print(
                    f"Last OHLC  : "
                    f"O={last['open']} "
                    f"H={last['high']} "
                    f"L={last['low']} "
                    f"C={last['close']}"
                )

            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()