from app.auth.jwt_handler import (
    create_access_token,
    decode_token,
)

token = create_access_token({"sub": "1"})

print(token)
print()
print(decode_token(token))