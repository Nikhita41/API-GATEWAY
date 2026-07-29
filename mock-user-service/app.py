from fastapi import FastAPI

app = FastAPI(title="Mock User Service")

@app.get("/health")
def health():
    return {"service": "user-service", "status": "healthy"}

@app.get("/users")
def get_users():
    return {
        "users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
    }
