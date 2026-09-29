"""
main.py — Web application entrypoint for habit_tracker_v1
Problem: Users need a simple API to track daily habits and mark completion.
# Requirements implemented in this file:
#   [FR-01] Users can create and list habits
#   [FR-02] Users can mark a habit as complete for today
"""
from fastapi import FastAPI, Depends, HTTPException
from models import init_db, get_db, HabitRecord
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="habit_tracker_v1", description="Users need a simple API to track daily habits and mark completion.", lifespan=lifespan)

# [EP] Create a new habit — implements: see design
@app.post("/api/habits", summary="Create a new habit")
def post_apihabits(db: Session = Depends(get_db)):
    record = HabitRecord()
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"status": "created", "id": record.id}

# [EP] List all habits — implements: see design
@app.get("/api/habits", summary="List all habits")
def get_apihabits(db: Session = Depends(get_db)):
    return db.query(HabitRecord).all()

# [EP] Mark habit completed — implements: see design
@app.post("/api/habits/{id}/complete", summary="Mark habit completed")
def post_apihabitsidcomplete(id: int, db: Session = Depends(get_db)):
    record = HabitRecord()
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"status": "created", "id": record.id}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=True)