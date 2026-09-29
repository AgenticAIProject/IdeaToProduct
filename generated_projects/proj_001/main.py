"""
main.py - FastAPI application entrypoint for proj_001
Problem Statement: Users often struggle to keep track of their daily habits and goals, leading to a lack of progress in personal development.
Architecture: The Habit Tracker system follows a three-tier distributed architecture:

**Presentation Layer**: Web and mobile client applications (responsive web UI and native/cross-platform mobile apps) that provide the user interface for habit management and progress visualization.

**Application Layer**: Backend REST API service that handles core business logic including user authentication, habit CRUD operations, progress calculation, and data retrieval. This layer enforces validation and business rules.

**Data Layer**: Relational database for persistent storage of user accounts, habits, daily completion records, and audit logs. Authentication tokens are managed securely with appropriate expiration policies.

**Key Interactions**:
1. Users authenticate via login/registration endpoints; successful authentication returns secure session/JWT tokens
2. Authenticated requests to habit endpoints include tokens; API validates token and user context
3. Clients fetch habit data and render UI locally; completion updates are sent to API and persisted
4. Progress queries aggregate completion records from database and return aggregated metrics/raw data for visualization
5. Data flows through validation layers at both API and database levels

The architecture is designed for scalability with stateless API servers (enabling horizontal scaling) and database indexing on frequently-queried fields (user_id, habit_id, completion_date).
"""
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager

from models import init_db, get_db, Item, UserRecord
from schemas import ItemCreate, ItemResponse, UserCreate, UserResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database tables on startup
    init_db()
    yield


app = FastAPI(
    title="Proj_001 API",
    description="Auto-generated implementation for proj_001",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
def root():
    return {
        "project": "proj_001",
        "status": "online",
        "endpoints": ["/health", "/docs", "/api/items", "/api/users"]
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "project_id": "proj_001"}


# --- Items CRUD Endpoints ---

@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    item = Item(
        title=payload.title,
        category=payload.category,
        description=payload.description,
        status=payload.status
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/items", response_model=list[ItemResponse])
def list_items(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Item).offset(skip).limit(limit).all()


@app.get("/api/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# --- Users Endpoints ---

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(UserRecord).filter(UserRecord.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = UserRecord(name=payload.name, email=payload.email, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/users", response_model=list[UserResponse])
def list_users(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(UserRecord).offset(skip).limit(limit).all()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
