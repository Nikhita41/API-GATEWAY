import psycopg2

HOST = "127.0.0.1"
PORT = 5432
DB = "gateway_db"
USER = "gateway_user"
PASSWORD = "test123"

print(repr(HOST))
print(repr(USER))
print(repr(PASSWORD))

conn = psycopg2.connect(
    host=HOST,
    port=PORT,
    dbname=DB,
    user=USER,
    password=PASSWORD,
)

print("Connected!")