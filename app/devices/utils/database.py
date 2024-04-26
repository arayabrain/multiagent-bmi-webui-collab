from tinydb import Query, TinyDB


class DatabaseManager:
    def __init__(self, db_path):
        self.db = TinyDB(db_path)
        self.query = Query()

    def update_recording_info(self, user_id, exp_id):
        self.db.upsert(
            {
                "data_id": "latest_recording",
                "user_id": user_id,
                "exp_id": exp_id,
            },
            self.query.data_id == "latest_recording",
        )

    def update_model_path(self, user_id, path):
        self.db.upsert(
            {
                "data_id": user_id,
                "path": path,
            },
            self.query.data_id == user_id,
        )

    def get_recording_info(self):
        data = self.db.get(self.query.data_id == "latest_recording")
        if data is None:
            raise ValueError("No recording found")
        return data["user_id"], data["exp_id"]

    def get_model_path(self, user_id):
        data = self.db.get(self.query.data_id == user_id)
        if data is None:
            raise ValueError(f"No user found for {user_id}")
        return data["path"]
