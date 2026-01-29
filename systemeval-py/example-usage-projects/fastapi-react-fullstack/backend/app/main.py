from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Fullstack Backend")

# In-memory store (no real database needed for the example)
USERS = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
]

_next_id = 3


class UserCreate(BaseModel):
    name: str
    email: str


@app.get("/health")
def health():
    return {"status": "healthy", "service": "backend"}


@app.get("/api/users")
def list_users():
    return USERS


@app.post("/api/users", status_code=201)
def create_user(user: UserCreate):
    global _next_id
    new_user = {"id": _next_id, "name": user.name, "email": user.email}
    USERS.append(new_user)
    _next_id += 1
    return new_user


@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    for user in USERS:
        if user["id"] == user_id:
            return user
    raise HTTPException(status_code=404, detail="User not found")
