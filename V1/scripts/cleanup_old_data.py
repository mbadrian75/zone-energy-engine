from pymongo import MongoClient


MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "market_data"
OLD_PREFIX = "tf_"


def main():
    client = MongoClient(MONGO_URI)

    try:
        # تست اتصال
        client.admin.command("ping")
        print("MongoDB connection: OK")

        db = client[DATABASE_NAME]

        all_collections = db.list_collection_names()

        old_collections = sorted(
            name for name in all_collections
            if name.startswith(OLD_PREFIX)
        )

        print("\nCollections that will be deleted:")

        if not old_collections:
            print("No tf_ collections found.")
            return

        for name in old_collections:
            print(f"  - {name}")

        print(f"\nTotal: {len(old_collections)}")

        # برای جلوگیری از حذف اشتباهی
        confirmation = input(
            '\nType DELETE to permanently remove these collections: '
        )

        if confirmation != "DELETE":
            print("\nCancelled. Nothing was deleted.")
            return

        print("\nDeleting...")

        for name in old_collections:
            db.drop_collection(name)
            print(f"DELETED: {name}")

        print("\nRemaining collections:")

        remaining = sorted(db.list_collection_names())

        for name in remaining:
            print(f"  - {name}")

        print("\nCleanup completed.")

    finally:
        client.close()


if __name__ == "__main__":
    main()