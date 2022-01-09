import os
import psycopg2

from config import DATABASE_URL

if os.environ.get("HEROKU"):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
else:
    conn = psycopg2.connect(DATABASE_URL)

cur = conn.cursor()

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
conn.commit()
