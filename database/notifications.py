import sqlite3
import json


class NotificationsDB:
    def __init__(self, db_file: str):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()

    def create_table(self):
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS notifications(
                        key TEXT PRIMARY KEY,
                        text TEXT NOT NULL
                    );
                """
            )

    def get_text(self, key: str) -> str | None:
        self.create_table()
        with self.connection:
            row = self.cursor.execute("SELECT text FROM notifications WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            return str(row[0])

    def set_text(self, key: str, text: str):
        self.create_table()
        with self.connection:
            self.cursor.execute(
                "INSERT INTO notifications(key, text) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET text=excluded.text",
                (key, text),
            )

    # --- Scheduled notifications management ---

    def _ensure_scheduled_table(self):
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS scheduled_notifications(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        message TEXT NOT NULL,
                        time TEXT NOT NULL,
                        groups TEXT NOT NULL,
                        mention_mode TEXT NOT NULL,
                        manual_mentions TEXT DEFAULT '',
                        last_sent TEXT,
                        builtin_key TEXT,
                        enabled INTEGER DEFAULT 1,
                        is_one_time INTEGER DEFAULT 0
                    );
                """
            )
            try:
                self.cursor.execute("ALTER TABLE scheduled_notifications ADD COLUMN description TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE scheduled_notifications ADD COLUMN builtin_key TEXT")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE scheduled_notifications ADD COLUMN enabled INTEGER DEFAULT 1")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE scheduled_notifications ADD COLUMN is_one_time INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                self.cursor.execute("ALTER TABLE scheduled_notifications ADD COLUMN weekday_messages TEXT")
            except Exception:
                pass

    def list_scheduled_notifications(self):
        self._ensure_scheduled_table()
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, title, description, message, time, groups, mention_mode, manual_mentions, last_sent, builtin_key, enabled, is_one_time, weekday_messages "
                "FROM scheduled_notifications ORDER BY id ASC"
            ).fetchall()
        notifications = []
        for row in rows:
            try:
                raw_groups = json.loads(row[5]) if row[5] else []
            except json.JSONDecodeError:
                raw_groups = []
            groups = []
            for item in raw_groups:
                if isinstance(item, dict):
                    group_id = int(item.get('group_id'))
                    thread_id = item.get('thread_id')
                    thread_id = None if thread_id in (None, '', 0) else int(thread_id)
                else:
                    group_id = int(item)
                    thread_id = None
                groups.append({'group_id': group_id, 'thread_id': thread_id})
            # Парсим weekday_messages если есть
            weekday_messages = None
            if len(row) > 12 and row[12]:
                try:
                    weekday_messages = json.loads(row[12])
                except json.JSONDecodeError:
                    weekday_messages = None
            
            notifications.append({
                'id': int(row[0]),
                'title': str(row[1]),
                'description': '' if row[2] is None else str(row[2]),
                'message': str(row[3]),
                'time': str(row[4]),
                'groups': groups,
                'mention_mode': str(row[6]),
                'manual_mentions': '' if row[7] is None else str(row[7]),
                'last_sent': None if row[8] is None else str(row[8]),
                'builtin_key': None if len(row) < 10 or row[9] is None else str(row[9]),
                'enabled': bool(row[10]) if len(row) > 10 and row[10] is not None else True,
                'is_one_time': bool(row[11]) if len(row) > 11 and row[11] is not None else False,
                'weekday_messages': weekday_messages,
            })
        return notifications

    def get_scheduled_notification(self, notif_id: int):
        self._ensure_scheduled_table()
        with self.connection:
            row = self.cursor.execute(
                "SELECT id, title, description, message, time, groups, mention_mode, manual_mentions, last_sent, builtin_key, enabled, is_one_time, weekday_messages "
                "FROM scheduled_notifications WHERE id=?",
                (notif_id,),
            ).fetchone()
        if not row:
            return None
        try:
            raw_groups = json.loads(row[5]) if row[5] else []
        except json.JSONDecodeError:
            raw_groups = []
        groups = []
        for item in raw_groups:
            if isinstance(item, dict):
                group_id = int(item.get('group_id'))
                thread_id = item.get('thread_id')
                thread_id = None if thread_id in (None, '', 0) else int(thread_id)
            else:
                group_id = int(item)
                thread_id = None
            groups.append({'group_id': group_id, 'thread_id': thread_id})
        # Парсим weekday_messages если есть
        weekday_messages = None
        if len(row) > 12 and row[12]:
            try:
                weekday_messages = json.loads(row[12])
            except json.JSONDecodeError:
                weekday_messages = None
        
        return {
            'id': int(row[0]),
            'title': str(row[1]),
            'description': '' if row[2] is None else str(row[2]),
            'message': str(row[3]),
            'time': str(row[4]),
            'groups': groups,
            'mention_mode': str(row[6]),
            'manual_mentions': '' if row[7] is None else str(row[7]),
            'last_sent': None if row[8] is None else str(row[8]),
            'builtin_key': None if len(row) < 10 or row[9] is None else str(row[9]),
            'enabled': bool(row[10]) if len(row) > 10 and row[10] is not None else True,
            'is_one_time': bool(row[11]) if len(row) > 11 and row[11] is not None else False,
            'weekday_messages': weekday_messages,
        }

    def create_scheduled_notification(
        self,
        title: str,
        description: str,
        message: str,
        time_value: str,
        groups: list,
        mention_mode: str,
        manual_mentions: str = '',
        builtin_key: str | None = None,
        enabled: bool = True,
        is_one_time: bool = False,
        weekday_messages: dict | None = None
    ) -> int:
        self._ensure_scheduled_table()
        formatted_groups = []
        for entry in groups:
            if isinstance(entry, dict):
                group_id = int(entry.get('group_id'))
                thread_id = entry.get('thread_id')
                formatted_groups.append({
                    'group_id': group_id,
                    'thread_id': None if thread_id in (None, '', 0) else int(thread_id)
                })
            else:
                formatted_groups.append({'group_id': int(entry), 'thread_id': None})
        groups_json = json.dumps(formatted_groups)
        weekday_messages_json = json.dumps(weekday_messages) if weekday_messages else None
        with self.connection:
            self.cursor.execute(
                """INSERT INTO scheduled_notifications
                    (title, description, message, time, groups, mention_mode, manual_mentions, builtin_key, enabled, is_one_time, weekday_messages)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, description, message, time_value, groups_json, mention_mode, manual_mentions, builtin_key, 1 if enabled else 0, 1 if is_one_time else 0, weekday_messages_json),
            )
            return self.cursor.lastrowid

    def update_scheduled_notification(self, notif_id: int, **fields):
        if not fields:
            return
        self._ensure_scheduled_table()
        allowed = {'title', 'description', 'message', 'time', 'groups', 'mention_mode', 'manual_mentions', 'last_sent', 'builtin_key', 'enabled', 'is_one_time', 'weekday_messages'}
        set_parts = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == 'groups':
                formatted_groups = []
                for entry in value:
                    if isinstance(entry, dict):
                        group_id = int(entry.get('group_id'))
                        thread_id = entry.get('thread_id')
                        formatted_groups.append({
                            'group_id': group_id,
                            'thread_id': None if thread_id in (None, '', 0) else int(thread_id)
                        })
                    else:
                        formatted_groups.append({'group_id': int(entry), 'thread_id': None})
                value = json.dumps(formatted_groups)
            elif key in {'enabled', 'is_one_time'}:
                value = 1 if value else 0
            elif key == 'weekday_messages':
                value = json.dumps(value) if value else None
            set_parts.append(f"{key}=?")
            values.append(value)
        if not set_parts:
            return
        values.append(notif_id)
        with self.connection:
            self.cursor.execute(
                f"UPDATE scheduled_notifications SET {', '.join(set_parts)} WHERE id=?",
                values,
            )

    def delete_scheduled_notification(self, notif_id: int):
        self._ensure_scheduled_table()
        with self.connection:
            self.cursor.execute("DELETE FROM scheduled_notifications WHERE id=?", (notif_id,))

    def update_notification_last_sent(self, notif_id: int, last_sent: str):
        self.update_scheduled_notification(notif_id, last_sent=last_sent)

    def _ensure_thread_message_table(self):
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS thread_messages(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        thread_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """
            )

    def add_thread_message(self, chat_id: int, thread_id: int, message_id: int, created_at: str):
        self._ensure_thread_message_table()
        with self.connection:
            self.cursor.execute(
                """INSERT INTO thread_messages(chat_id, thread_id, message_id, created_at)
                    VALUES(?, ?, ?, ?)""",
                (chat_id, thread_id, message_id, created_at),
            )

    def get_thread_messages_older_than(self, cutoff_iso: str):
        self._ensure_thread_message_table()
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, chat_id, thread_id, message_id, created_at FROM thread_messages WHERE created_at <= ?",
                (cutoff_iso,),
            ).fetchall()
        return [
            {
                'id': int(row[0]),
                'chat_id': int(row[1]),
                'thread_id': int(row[2]),
                'message_id': int(row[3]),
                'created_at': str(row[4]),
            }
            for row in rows
        ]

    def get_thread_messages_by_chat_and_thread(self, chat_id: int, thread_id: int):
        """Получить все сообщения из конкретной темы."""
        self._ensure_thread_message_table()
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, chat_id, thread_id, message_id, created_at FROM thread_messages WHERE chat_id = ? AND thread_id = ?",
                (chat_id, thread_id),
            ).fetchall()
        return [
            {
                'id': int(row[0]),
                'chat_id': int(row[1]),
                'thread_id': int(row[2]),
                'message_id': int(row[3]),
                'created_at': str(row[4]),
            }
            for row in rows
        ]

    def remove_thread_message(self, record_id: int):
        self._ensure_thread_message_table()
        with self.connection:
            self.cursor.execute("DELETE FROM thread_messages WHERE id=?", (record_id,))

    # --- Threads management ---

    def _ensure_threads_table(self):
        """Создает таблицу для хранения сохраненных тем."""
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS saved_threads(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER NOT NULL,
                        thread_id INTEGER NOT NULL,
                        thread_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(group_id, thread_id)
                    );
                """
            )

    def add_thread(self, group_id: int, thread_id: int, thread_name: str, created_at: str) -> int:
        """Добавляет тему в БД. Возвращает ID записи."""
        self._ensure_threads_table()
        with self.connection:
            try:
                self.cursor.execute(
                    """INSERT INTO saved_threads(group_id, thread_id, thread_name, created_at)
                        VALUES(?, ?, ?, ?)""",
                    (group_id, thread_id, thread_name, created_at),
                )
                return self.cursor.lastrowid
            except sqlite3.IntegrityError:
                # Тема уже существует, обновляем название
                self.cursor.execute(
                    """UPDATE saved_threads SET thread_name=? WHERE group_id=? AND thread_id=?""",
                    (thread_name, group_id, thread_id),
                )
                row = self.cursor.execute(
                    "SELECT id FROM saved_threads WHERE group_id=? AND thread_id=?",
                    (group_id, thread_id),
                ).fetchone()
                return row[0] if row else None

    def get_threads_by_group(self, group_id: int) -> list[dict]:
        """Получает все сохраненные темы для группы."""
        self._ensure_threads_table()
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, group_id, thread_id, thread_name, created_at FROM saved_threads WHERE group_id=? ORDER BY thread_name ASC",
                (group_id,),
            ).fetchall()
        return [
            {
                'id': int(row[0]),
                'group_id': int(row[1]),
                'thread_id': int(row[2]),
                'thread_name': str(row[3]),
                'created_at': str(row[4]),
            }
            for row in rows
        ]

    def get_thread(self, group_id: int, thread_id: int) -> dict | None:
        """Получает тему по group_id и thread_id."""
        self._ensure_threads_table()
        with self.connection:
            row = self.cursor.execute(
                "SELECT id, group_id, thread_id, thread_name, created_at FROM saved_threads WHERE group_id=? AND thread_id=?",
                (group_id, thread_id),
            ).fetchone()
        if not row:
            return None
        return {
            'id': int(row[0]),
            'group_id': int(row[1]),
            'thread_id': int(row[2]),
            'thread_name': str(row[3]),
            'created_at': str(row[4]),
        }

    def delete_thread(self, thread_db_id: int):
        """Удаляет тему по ID записи в БД."""
        self._ensure_threads_table()
        with self.connection:
            self.cursor.execute("DELETE FROM saved_threads WHERE id=?", (thread_db_id,))


