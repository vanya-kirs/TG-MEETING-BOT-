import sqlite3

class Database1:
    def __init__(self,db_file):
        self.connection=sqlite3.connect(db_file)
        self.cursor=self.connection.cursor()

    def create_table_meet(self):
        with self.connection:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS meet(
                                       date VARCHAR (60),
                                       time VARCHAR (60),
                                       nickname VARCHAR (60),
                                       zapis VARCHAR (60),
                                       client VARCHAR (60));
                                    """)

    def add_name_meet(self, name):
        with self.connection:
            return self.cursor.execute("INSERT INTO `meet` (`nickname`) VALUES(?)",(name,))

    def add_date_meet(self, name, date):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `date` =? WHERE `nickname`=?",(date, name,))

    def add_time_meet(self, name, time):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `time` =? WHERE `nickname`=?",(time, name,))


    def delete_meet(self, name):
        with self.connection:
            return self.cursor.execute("DELETE FROM `meet` WHERE `nickname`=?",(name,))

    def name_meet(self):
        with self.connection:
            x=self.cursor.execute("SELECT * FROM `meet`")
            meet=[]
            for meets in x:
                meet.append(meets[4])
                meet.append(meets[2])
                meet.append(meets[1])
                meet.append(meets[0])
            return meet

    def name_meet1(self):
        with self.connection:
            x=self.cursor.execute("SELECT * FROM `meet`")
            meet=[]
            for meets in x:
                meet.append(meets[3])
                meet.append(meets[2])
                meet.append(meets[1])
                meet.append(meets[0])
            return meet

    def meet_exists(self, chose):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM `meet` WHERE `nickname` =?", (chose,)).fetchall()
            return bool(len(result))

    def add_zapis_meet(self, status, name):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `zapis` =? WHERE `nickname`=?",(status, name,))

    def add_client_meet(self, status, name):
        with self.connection:
            return self.cursor.execute("UPDATE `meet` SET `client` =? WHERE `nickname`=?",(status, name,))

    def client_exists(self):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM `meet`")
            client=[]
            for clients in result:
                client.append(clients[4])
            return client

    def meet_by_client(self, name):
        with self.connection:
            result= self.cursor.execute("SELECT `nickname` FROM `meet` WHERE `client`=?",(name,))
            for row in result:
                name = str(row[0])
            return name

    def count_meet(self):
        with self.connection:
            x=self.cursor.execute("SELECT `nickname` FROM `meet`")
            meet=[]
            for meets in x:
                for count in meets:
                    meet.append(int(count))
            return meet

    def check_dr(self):
        with self.connection:
            x=self.cursor.execute("SELECT `birthday` FROM `users`")
            meet=[]
            for meets in x:
                for count in meets:
                    meet.append(count)
            return meet

    def select_client_meet(self, zapis):
        with self.connection:
            x=self.cursor.execute("SELECT `client` FROM `meet` WHERE `zapis`=?",(zapis,))
            clients=[]
            for client in x:
                for count in client:
                    clients.append(count)
            return clients

    def select_date_client(self, client):
        with self.connection:
            x=self.cursor.execute("SELECT `date` FROM `meet` WHERE `client`=?",(client,))
            date={}
            for clients in x:
                for count in clients:
                    date[client]=count
            return date

    def select_time_client(self, client):
        with self.connection:
            x=self.cursor.execute("SELECT `time` FROM `meet` WHERE `client`=?",(client,))
            date=[]
            for clients in x:
                for count in clients:
                    date.append(count)
            return date[0]

    def get_id(self, nick):
        with self.connection:
            result = self.cursor.execute("SELECT `user_id` FROM `users` WHERE `nickname` = ?", (nick,)).fetchall()
            if not result:  # Если пользователь не найден
                return None
            return str(result[0][0])  # Возвращаем ID пользователя

    def get_nick_by_birth(self, birth):
        with self.connection:
            result=self.cursor.execute("SELECT `nickname` FROM `users` WHERE `birthday`=?",(birth,))
            for row in result:
                birth=str(row[0])
            return birth

    def all_meet(self):
        with self.connection:
            result= self.cursor.execute("SELECT `nickname` FROM `meet`")
            meets=[]
            for meet in result:
                for mt in meet:
                    meets.append(mt)
            return meets

    def get_date_by_name(self, name):
        with self.connection:
            result=self.cursor.execute("SELECT `date` FROM `meet` WHERE `nickname`=?",(name,))
            for row in result:
                date=str(row[0])
            return date

    def select_delete_client(self, nick):
        with self.connection:
            result=self.cursor.execute("SELECT `client` FROM `meet` WHERE `nickname` = ?",(nick,)).fetchall()
            for row in result:
                nickname=str(row[0])
            return nickname

    def all_time_meet(self):
        with self.connection:
            x=self.cursor.execute("SELECT  `date` FROM `meet`")
            dates = []
            for time in x:
                for i in time:
                    dates.append(i)
            return dates

    def time_meet1(self, data):
        with self.connection:
            x=self.cursor.execute("SELECT `time` FROM `meet` WHERE `date` =?",(data,))
            timess=[]
            for time in x:
                for i in time:
                    timess.append(i)
            return timess