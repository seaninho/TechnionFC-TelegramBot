import os
import psycopg2

from config import DATABASE_URL


class PostgreSqlDb:
    """This class holds all relevant SQL database functions"""
    def __init__(self):
        self.init_connection()

    def init_connection(self):
        """Initialize a new connection to the PostgreSQL database"""
        self._connect()
        self._create_tables()

    def get_connection(self):
        """Get the PostgreSQL database connection"""
        return self._connection

    def restart_connection(self):
        """Restart the PostgreSQL database connection"""
        # Close the old connection
        if self._connection:
            if self._connection.cursor():
                self._connection.cursor().close()
            self._connection.close()
        # Reconnect
        self.init_connection()

    def _connect(self):
        """Create a connection to the PostgreSQL database"""
        if os.environ.get("HEROKU"):
            self._connection = psycopg2.connect(DATABASE_URL, sslmode='require')
        self._connection = psycopg2.connect(DATABASE_URL)

    def _create_tables(self):
        """Create database tables"""
        cur = self._connection.cursor()

        # cur.execute("DROP TABLE playing")
        cur.execute("CREATE TABLE IF NOT EXISTS PLAYING ("
                    "   user_id BIGINT,"
                    "   user_first_name VARCHAR,"
                    "   user_last_name VARCHAR,"
                    "   user_username VARCHAR,"
                    "   player_liable BOOLEAN NOT NULL,"
                    "   player_approved BOOLEAN NOT NULL,"
                    "   player_match_ball BOOLEAN NOT NULL,"
                    "   PRIMARY KEY (user_id, user_first_name, user_last_name, user_username))")

        cur.execute("CREATE TABLE IF NOT EXISTS INVITED ("            
                    "   username VARCHAR PRIMARY KEY)")

        cur.execute("CREATE TABLE IF NOT EXISTS ASKED ("            
                    "   user_id_or_name VARCHAR PRIMARY KEY)")
        cur.close()
        self._connection.commit()
