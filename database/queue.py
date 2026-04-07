import sqlite3


WEEKDAY_WINDOWS = {
    'Понедельник': [
        '06:00-09:00', '09:00-13:00', '13:00-16:00', '16:00-19:00', '19:00-22:00', '22:00-00:00'
    ],
    'Вторник': [
        '06:00-09:00', '09:00-13:00', '13:00-16:00', '16:00-19:00', '19:00-22:00', '22:00-00:00'
    ],
    'Среда': [
        '06:00-09:00', '09:00-13:00', '13:00-16:00', '16:00-19:00', '19:00-22:00', '22:00-00:00'
    ],
    'Четверг': [
        '06:00-09:00', '09:00-13:00', '13:00-16:00', '16:00-19:00', '19:00-22:00', '22:00-00:00'
    ],
    'Пятница': [
        '06:00-09:00', '09:00-13:00', '13:00-16:00', '16:00-19:00', '19:00-22:00', '22:00-00:00'
    ],
    'Суббота': [
        '06:00-09:00', '09:00-13:00', '13:00-17:00', '17:00-21:00', '21:00-00:00'
    ],
    'Воскресенье': [
        '06:00-09:00', '09:00-13:00', '13:00-17:00', '17:00-21:00', '21:00-00:00'
    ],
}


class QueueDB:
    def __init__(self, db_file: str):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()

    def create_table_queue(self):
        with self.connection:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS queue_schedule(
                        id INTEGER PRIMARY KEY,
                        day VARCHAR(20) NOT NULL,
                        window VARCHAR(20) NOT NULL,
                        trainer_id INTEGER,
                        UNIQUE(day, window)
                    );
                """
            )
            # Таблица назначений (многие-ко-многим для поддержки до 2 тренеров на слот)
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS queue_assignments(
                        id INTEGER PRIMARY KEY,
                        day VARCHAR(20) NOT NULL,
                        window VARCHAR(20) NOT NULL,
                        trainer_id INTEGER NOT NULL,
                        UNIQUE(day, window, trainer_id)
                    );
                """
            )

    def ensure_defaults(self):
        self.create_table_queue()
        with self.connection:
            # Обновим старые временные окна будней на новые
            weekday_days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']
            replacements = {
                '19:00-21:00': '19:00-22:00',
                '21:00-00:00': '22:00-00:00',
            }
            for day in weekday_days:
                for old_window, new_window in replacements.items():
                    self.cursor.execute(
                        "UPDATE `queue_schedule` SET `window`=? WHERE `day`=? AND `window`=?",
                        (new_window, day, old_window),
                    )
                    self.cursor.execute(
                        "UPDATE `queue_assignments` SET `window`=? WHERE `day`=? AND `window`=?",
                        (new_window, day, old_window),
                    )
            for day, windows in WEEKDAY_WINDOWS.items():
                for win in windows:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO `queue_schedule` (`day`, `window`, `trainer_id`) VALUES(?, ?, ?)",
                        (day, win, None),
                    )

    def list_day(self, day: str):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id, window, trainer_id FROM `queue_schedule` WHERE `day`=? ORDER BY id ASC",
                (day,),
            ).fetchall()
            return [(int(r[0]), str(r[1]), (None if r[2] is None else int(r[2]))) for r in rows]

    def set_trainer(self, slot_id: int, trainer_id: int | None):
        with self.connection:
            return self.cursor.execute(
                "UPDATE `queue_schedule` SET `trainer_id`=? WHERE `id`=?",
                (trainer_id, slot_id),
            )

    def get_all(self):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT day, window, trainer_id FROM `queue_schedule` ORDER BY day, id"
            ).fetchall()
            return [(str(r[0]), str(r[1]), (None if r[2] is None else int(r[2]))) for r in rows]

    # ------ Мультиназначения ------
    def get_trainers_for(self, day: str, window: str):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT trainer_id FROM `queue_assignments` WHERE `day`=? AND `window`=? ORDER BY id ASC",
                (day, window),
            ).fetchall()
            return [int(r[0]) for r in rows]

    def add_trainer_to_slot(self, day: str, window: str, trainer_id: int):
        with self.connection:
            return self.cursor.execute(
                "INSERT OR IGNORE INTO `queue_assignments` (`day`, `window`, `trainer_id`) VALUES(?, ?, ?)",
                (day, window, trainer_id),
            )

    def replace_second_trainer(self, day: str, window: str, trainer_id: int):
        with self.connection:
            # Получим существующие записи, если >=2, заменим вторую
            rows = self.cursor.execute(
                "SELECT id, trainer_id FROM `queue_assignments` WHERE `day`=? AND `window`=? ORDER BY id ASC",
                (day, window),
            ).fetchall()
            if not rows:
                # если нет записей — просто добавим
                self.cursor.execute(
                    "INSERT OR IGNORE INTO `queue_assignments` (`day`, `window`, `trainer_id`) VALUES(?, ?, ?)",
                    (day, window, trainer_id),
                )
                return
            if len(rows) == 1:
                # если один — добавим второго
                self.cursor.execute(
                    "INSERT OR IGNORE INTO `queue_assignments` (`day`, `window`, `trainer_id`) VALUES(?, ?, ?)",
                    (day, window, trainer_id),
                )
                return
            # если два и более — заменим второй
            second_id = int(rows[1][0])
            self.cursor.execute(
                "UPDATE `queue_assignments` SET `trainer_id`=? WHERE id=?",
                (trainer_id, second_id),
            )

    def ensure_two_limit(self, day: str, window: str):
        with self.connection:
            rows = self.cursor.execute(
                "SELECT id FROM `queue_assignments` WHERE `day`=? AND `window`=? ORDER BY id ASC",
                (day, window),
            ).fetchall()
            if len(rows) <= 2:
                return
            # оставим первые 2, остальные удалим
            ids_to_keep = {int(rows[0][0]), int(rows[1][0])}
            self.cursor.execute(
                f"DELETE FROM `queue_assignments` WHERE `day`=? AND `window`=? AND id NOT IN ({','.join(['?','?'])})",
                (day, window, *ids_to_keep),
            )

    def remove_trainer_from_slot(self, day: str, window: str, trainer_id: int):
        with self.connection:
            return self.cursor.execute(
                "DELETE FROM `queue_assignments` WHERE `day`=? AND `window`=? AND `trainer_id`=?",
                (day, window, trainer_id),
            )

    def clear_slot(self, day: str, window: str):
        with self.connection:
            return self.cursor.execute(
                "DELETE FROM `queue_assignments` WHERE `day`=? AND `window`=?",
                (day, window),
            )


