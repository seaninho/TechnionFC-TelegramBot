import os
import psycopg
import logging

from config import DATABASE_URL

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)

logger = logging.getLogger(__name__)

class PostgreSqlDb:
    """This class holds all relevant SQL database functions"""

    def __init__(self):
        self._connection = None
        self.init_connection()

    def init_connection(self):
        """Initialize a new connection to the PostgreSQL database"""
        self._connect()
        self._create_tables()

    def get_connection(self):
        """Get the PostgreSQL database connection with health check"""
        if not self._is_connection_alive():
            logger.warning("Database connection is not alive, reconnecting...")
            self.restart_connection()
        return self._connection

    def restart_connection(self):
        """Restart the PostgreSQL database connection"""
        # Close the old connection
        try:
            if self._connection and not self._connection.closed:
                try:
                    self._connection.close()
                except Exception as e:
                    logger.error(f"Error closing old connection: {e}")
        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")

        # Reconnect
        self._connection = None
        self.init_connection()

    def _is_connection_alive(self):
        """Check if the database connection is still alive"""
        if self._connection is None:
            return False
        if self._connection.closed:
            return False
        try:
            # Try to execute a simple query to verify connection
            with self._connection.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except (psycopg.OperationalError, psycopg.InterfaceError, AttributeError):
            return False

    def _connect(self):
        """Create a connection to the PostgreSQL database"""
        try:
            # Parse DATABASE_URL if needed for Heroku
            conninfo = DATABASE_URL

            # psycopg3 automatically handles sslmode if in connection string
            # For Heroku, ensure sslmode=require is in the URL or add it
            if os.environ.get("HEROKU"):
                if "sslmode" not in conninfo:
                    # Add sslmode parameter
                    separator = "&" if "?" in conninfo else "?"
                    conninfo = f"{conninfo}{separator}sslmode=require"

            self._connection = psycopg.connect(
                conninfo,
                connect_timeout=10,
                autocommit=False
            )

            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _create_tables(self):
        """Create database tables"""
        try:
            with self._connection.cursor() as cur:
                # cur.execute("DROP TABLE playing")
                cur.execute("CREATE TABLE IF NOT EXISTS PLAYERS ("
                            "   user_id BIGINT,"
                            "   user_first_name VARCHAR,"
                            "   user_last_name VARCHAR,"
                            "   user_username VARCHAR,"
                            "   player_banned BOOLEAN NOT NULL,"
                            "   player_ban_duration INT NOT NULL,"
                            "   player_rating NUMERIC(3, 2) NOT NULL CHECK (player_rating BETWEEN 1.00 AND 5.00),"
                            "   player_rated_by BIGINT[] NOT NULL,"
                            "   PRIMARY KEY (user_id, user_first_name, user_last_name, user_username))")

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

            self._connection.commit()
            logger.info("Database tables created/verified successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            self._connection.rollback()
            raise
