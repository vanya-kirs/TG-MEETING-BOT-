import sqlite3
class Database:
    def __init__(self,db_file):
        self.connection=sqlite3.connect(db_file)
        self.cursor=self.connection.cursor()

    def create_table_client(self):
        with self.connection:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS users(
                           id INTEGER PRIMARY KEY,
                           user_id  NOT NULL,
                           nickname VARCHAR (60),
                           birthday VARCHAR (60),
                           signup VARCHAR DEFAULT setnickname,
                           username VARCHAR (60),
                           phone VARCHAR (32),
                           employment_type VARCHAR(10),
                           email VARCHAR(120),
                           role VARCHAR (20) DEFAULT client);
                        """)
            # На случай существующей таблицы без новых столбцов — попытка добавить
            try:
                self.cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(60)")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT client")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(32)")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE users ADD COLUMN employment_type VARCHAR(10)")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(120)")
            except Exception:
                pass

    def add_user(self, user_id):
        with self.connection:
            return self.cursor.execute("INSERT INTO `users` (`user_id`) VALUES(?)",(user_id,))


    def user_exists(self,user_id):
        with self.connection:
            result=self.cursor.execute("SELECT * FROM `users` WHERE `user_id` =?",(user_id,)).fetchall()
            return bool(len(result))

    def set_nickname(self,user_id,nickname):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `nickname` =? WHERE `user_id`=?",(nickname,user_id,))

    def set_birthday(self,user_id,date):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `birthday` =? WHERE `user_id`=?",(date,user_id,))

    def set_birthday_by_id(self, trainer_id: int, date: str):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `birthday` =? WHERE `id`=?", (date, trainer_id,))

    def change_nickname_in_meet(self,new_nickname , old_nickname):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `client` =? WHERE `client`=?",(new_nickname,old_nickname,))

    def change_user_nickname(self,new_nickname , old_nickname):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `nickname` =? WHERE `nickname`=?",(new_nickname,old_nickname,))

    def get_signup(self, user_id):
        with self.connection:
            result=self.cursor.execute("SELECT `signup` FROM `users` WHERE `user_id` = ?",(user_id,)).fetchall()
            for row in result:
                signup=str(row[0])
            return signup

    def set_signup(self,user_id, signup):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `signup` =? WHERE `user_id`=?",(signup,user_id,))

    def get_nickname(self, user_id):
        with self.connection:
            result=self.cursor.execute("SELECT `nickname` FROM `users` WHERE `user_id` = ?",(user_id,)).fetchall()
            for row in result:
                nickname=str(row[0])
            return nickname

    # ----- Username / Trainers management based on users -----
    def set_username(self, user_id, username):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `username` =? WHERE `user_id`=?", (username, user_id,))

    def get_username(self, user_id):
        with self.connection:
            result=self.cursor.execute("SELECT `username` FROM `users` WHERE `user_id` = ?",(user_id,)).fetchall()
            for row in result:
                return str(row[0])
            return None

    def set_phone(self, user_id: int, phone: str):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `phone`=? WHERE `user_id`=?", (phone, user_id,))

    def get_phone(self, user_id: int):
        with self.connection:
            row = self.cursor.execute("SELECT `phone` FROM `users` WHERE `user_id`=?", (user_id,)).fetchone()
            if not row:
                return None
            return None if row[0] is None else str(row[0])

    def set_employment_type(self, user_id: int, emp_type: str):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `employment_type`=? WHERE `user_id`=?", (emp_type, user_id,))

    def get_employment_type(self, user_id: int):
        with self.connection:
            row = self.cursor.execute("SELECT `employment_type` FROM `users` WHERE `user_id`=?", (user_id,)).fetchone()
            if not row:
                return None
            return None if row[0] is None else str(row[0])

    def set_email(self, user_id: int, email: str):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `email`=? WHERE `user_id`=?", (email, user_id,))

    def get_email(self, user_id: int):
        with self.connection:
            row = self.cursor.execute("SELECT `email` FROM `users` WHERE `user_id`=?", (user_id,)).fetchone()
            if not row:
                return None
            return None if row[0] is None else str(row[0])

    def list_users_without_email(self):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT `user_id` FROM `users` WHERE (`email` IS NULL OR TRIM(`email`) = '') AND `signup`='done'"
            ).fetchall()
            return [int(r[0]) for r in rows if r[0] is not None]
    
    def list_all_users(self):
        """Возвращает список всех user_id зарегистрированных пользователей."""
        with self.connection:
            rows = self.cursor.execute(
                "SELECT `user_id` FROM `users` WHERE `signup`='done'"
            ).fetchall()
            return [int(r[0]) for r in rows if r[0] is not None]

    def get_username_by_nickname(self, nickname: str):
        with self.connection:
            row = self.cursor.execute("SELECT `username` FROM `users` WHERE `nickname`=?", (nickname,)).fetchone()
            if not row:
                return None
            return None if row[0] is None else str(row[0])

    def get_user_by_username(self, username):
        with self.connection:
            row = self.cursor.execute("SELECT id, user_id, nickname, username FROM `users` WHERE `username`=?", (username,)).fetchone()
            if not row:
                return None
            return (int(row[0]), row[1], str(row[2]), str(row[3]))

    def upsert_trainer(self, name, username):
        with self.connection:
            existing = self.get_user_by_username(username)
            if existing:
                # Обновим имя и роль
                self.cursor.execute("UPDATE `users` SET `nickname`=?, `role`='trainer' WHERE `username`=?", (name, username,))
                return existing[0]
            # Создадим запись без реального user_id (0), роль trainer
            self.cursor.execute("INSERT INTO `users` (`user_id`, `nickname`, `username`, `role`, `signup`) VALUES(?, ?, ?, 'trainer', 'done')", (0, name, username))
            return self.cursor.lastrowid

    def get_trainer_id_by_name(self, name: str):
        with self.connection:
            row = self.cursor.execute(
                "SELECT id FROM `users` WHERE `nickname` = ?",
                (name,)
            ).fetchone()
            if not row:
                return None
            return int(row[0])

    def list_trainers(self):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, nickname, username FROM `users` "
                "WHERE role='trainer' "
                "   OR (username IS NOT NULL AND TRIM(username) <> '') "
                "ORDER BY LOWER(COALESCE(nickname, '')) ASC, id ASC"
            ).fetchall()
            return [(int(r[0]), str(r[1] or ''), str(r[2] or '')) for r in rows]

    def get_trainer_details(self, trainer_id: int):
        row = self.cursor.execute(
            "SELECT id, user_id, nickname, birthday, username, phone, employment_type, email "
            "FROM `users` WHERE id=?",
            (trainer_id,),
        ).fetchone()
        if not row:
            return None
        keys = ['id', 'user_id', 'nickname', 'birthday', 'username', 'phone', 'employment_type', 'email']
        details = {key: row[idx] for idx, key in enumerate(keys)}
        extra = self.get_extra_record(trainer_id)
        if extra:
            details.update(extra)
        return details

    def update_trainer_field(self, trainer_id: int, field: str, value):
        allowed = {'nickname', 'birthday', 'username', 'phone', 'employment_type', 'email'}
        if field not in allowed:
            raise ValueError(f'Field {field} is not editable')
        with self.connection:
            self.cursor.execute(f"UPDATE `users` SET `{field}`=? WHERE id=?", (value, trainer_id))

    def demote_trainer(self, trainer_id: int):
        with self.connection:
            return self.cursor.execute("UPDATE `users` SET `role`='client' WHERE id=?", (trainer_id,))

    def delete_user_by_id(self, trainer_id: int):
        with self.connection:
            # First delete from trainer_extra table if exists
            self._ensure_extra()
            self.cursor.execute("DELETE FROM trainer_extra WHERE trainer_id=?", (trainer_id,))
            # Then delete from users table
            return self.cursor.execute("DELETE FROM `users` WHERE id=?", (trainer_id,))

    def delete_user_by_user_id(self, user_id: int):
        with self.connection:
            self.cursor.execute("DELETE FROM `users` WHERE `user_id`=?", (user_id,))

    # ----- Extra info (med/qual) tied to users.id -----
    def _ensure_extra(self):
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS trainer_extra(
                        trainer_id INTEGER PRIMARY KEY,
                        med_date TEXT,
                        qual_date TEXT,
                        med_last_notified TEXT,
                        qual_last_notified TEXT
                    );
                """
            )
            try:
                self.cursor.execute("ALTER TABLE trainer_extra ADD COLUMN med_last_notified TEXT")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE trainer_extra ADD COLUMN qual_last_notified TEXT")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE trainer_extra ADD COLUMN birthday_notifications_disabled INTEGER DEFAULT 0")
            except Exception:
                pass

    def set_med_date(self, trainer_id: int, date_str: str):
        self._ensure_extra()
        with self.connection:
            self.cursor.execute(
                "INSERT INTO trainer_extra (trainer_id, med_date, med_last_notified) VALUES(?, ?, NULL) "
                "ON CONFLICT(trainer_id) DO UPDATE SET med_date=excluded.med_date, med_last_notified=NULL",
                (trainer_id, date_str),
            )

    def set_qual_date(self, trainer_id: int, date_str: str):
        self._ensure_extra()
        with self.connection:
            self.cursor.execute(
                "INSERT INTO trainer_extra (trainer_id, qual_date, qual_last_notified) VALUES(?, ?, NULL) "
                "ON CONFLICT(trainer_id) DO UPDATE SET qual_date=excluded.qual_date, qual_last_notified=NULL",
                (trainer_id, date_str),
            )

    def set_med_notified(self, trainer_id: int, date_str: str | None):
        self._ensure_extra()
        with self.connection:
            self.cursor.execute(
                "UPDATE trainer_extra SET med_last_notified=? WHERE trainer_id=?",
                (date_str, trainer_id)
            )

    def set_qual_notified(self, trainer_id: int, date_str: str | None):
        self._ensure_extra()
        with self.connection:
            self.cursor.execute(
                "UPDATE trainer_extra SET qual_last_notified=? WHERE trainer_id=?",
                (date_str, trainer_id)
            )

    def set_birthday_notifications_disabled(self, trainer_id: int, disabled: bool):
        """Устанавливает флаг отключения поздравлений с днем рождения для тренера"""
        self._ensure_extra()
        with self.connection:
            self.cursor.execute(
                "INSERT INTO trainer_extra (trainer_id, birthday_notifications_disabled) VALUES(?, ?) "
                "ON CONFLICT(trainer_id) DO UPDATE SET birthday_notifications_disabled=excluded.birthday_notifications_disabled",
                (trainer_id, 1 if disabled else 0)
            )

    def is_birthday_notifications_disabled(self, trainer_id: int) -> bool:
        """Проверяет, отключены ли поздравления с днем рождения для тренера"""
        self._ensure_extra()
        with self.connection:
            row = self.cursor.execute(
                "SELECT birthday_notifications_disabled FROM trainer_extra WHERE trainer_id=?",
                (trainer_id,)
            ).fetchone()
            if not row or row[0] is None:
                return False
            return bool(row[0])

    def get_extra(self, trainer_id: int):
        self._ensure_extra()
        with self.connection:
            row = self.cursor.execute(
                "SELECT med_date, qual_date FROM trainer_extra WHERE trainer_id=?",
                (trainer_id,),
            ).fetchone()
            if not row:
                return None, None
            med, qual = row
            return (None if med is None else str(med)), (None if qual is None else str(qual))

    def get_extra_record(self, trainer_id: int):
        self._ensure_extra()
        with self.connection:
            row = self.cursor.execute(
                "SELECT med_date, qual_date, med_last_notified, qual_last_notified, birthday_notifications_disabled "
                "FROM trainer_extra WHERE trainer_id=?",
                (trainer_id,)
            ).fetchone()
            if not row:
                return None
            med, qual, med_notified, qual_notified, birthday_disabled = row
            return {
                'med_date': None if med is None else str(med),
                'qual_date': None if qual is None else str(qual),
                'med_last_notified': None if med_notified is None else str(med_notified),
                'qual_last_notified': None if qual_notified is None else str(qual_notified),
                'birthday_notifications_disabled': bool(birthday_disabled) if birthday_disabled is not None else False,
            }

    def list_extra(self):
        self._ensure_extra()
        with self.connection:
            rows = self.cursor.execute(
                "SELECT trainer_id, med_date, qual_date, med_last_notified, qual_last_notified FROM trainer_extra"
            ).fetchall()
            return [
                (
                    int(r[0]),
                    (None if r[1] is None else str(r[1])),
                    (None if r[2] is None else str(r[2])),
                    (None if r[3] is None else str(r[3])),
                    (None if r[4] is None else str(r[4])),
                )
                for r in rows
            ]

    def zapis_meet(self, user_name, chose):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `client` =? WHERE `nickname`=?",(chose, user_name,))

    def get_meet(self, name):
        with self.connection:
            result=self.cursor.execute("SELECT `client` FROM `meet` WHERE `nickname` = ?",(name,)).fetchall()
            for row in result:
                meet=str(row[0])
            return meet

    def update_zapis(self, nickname, null):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `client` =? WHERE `nickname`=?",(null, nickname,))

    def time_zapis(self, name):
        with self.connection:
            result= self.cursor.execute("SELECT `time` FROM `meet` WHERE `nickname`=?",(name,))
            for row in result:
                time = str(row[0])
            return time
    def date_zapis(self, name):
        with self.connection:
            result= self.cursor.execute("SELECT `date` FROM `meet` WHERE `nickname`=?",(name,))
            for row in result:
                date = str(row[0])
            return date

    def zapis_for_registration(self, name):
        with self.connection:
            result=self.cursor.execute("SELECT `zapis` FROM `meet` WHERE `nickname` = ?",(name,)).fetchall()
            for row in result:
                zapis=str(row[0])
            return zapis

