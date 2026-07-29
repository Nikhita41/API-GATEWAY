from fastapi import FastAPI

app = FastAPI(title="Mock Order Service")

@app.get("/health")
def health():
    return {"service": "order-service", "status": "healthy"}

@app.get("/orders")
def get_orders():
    return {
        "orders": [
            {"id": 101, "item": "Keyboard"},
            {"id": 102, "item": "Mouse"}
        ]
    }
