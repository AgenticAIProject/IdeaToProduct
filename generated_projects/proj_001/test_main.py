import pytest
import json
from main import app, db, Goal

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client

@pytest.fixture(autouse=True)
def cleanup():
    yield
    with app.app_context():
        db.drop_all()


def test_create_goal(client):
    response = client.post('/api/goals', json={'goal': 'Finish project'})
    assert response.status_code == 201
    assert 'goal' in response.get_json()


def test_create_duplicate_goal(client):
    client.post('/api/goals', json={'goal': 'Finish project'})
    response = client.post('/api/goals', json={'goal': 'Finish project'})
    assert response.status_code == 400
    assert 'message' in response.get_json()


def test_get_goals(client):
    client.post('/api/goals', json={'goal': 'Read a book'})
    response = client.get('/api/goals')
    assert response.status_code == 200
    assert len(response.get_json()) > 0


def test_delete_goal(client):
    response = client.post('/api/goals', json={'goal': 'Go for a run'})
    goal_id = response.get_json()['id']
    delete_response = client.delete(f'/api/goals/{goal_id}')
    assert delete_response.status_code == 204
    get_response = client.get('/api/goals')
    assert goal_id not in [goal['id'] for goal in get_response.get_json()]


def test_delete_non_existent_goal(client):
    response = client.delete('/api/goals/999')
    assert response.status_code == 404
    assert 'message' in response.get_json()


def test_update_goal_completion(client):
    response = client.post('/api/goals', json={'goal': 'Do laundry'})
    goal_id = response.get_json()['id']
    response = client.patch(f'/api/goals/{goal_id}', json={'completed': True})
    assert response.status_code == 200
    assert response.get_json()['completed'] is True


def test_get_completed_goals(client):
    client.post('/api/goals', json={'goal': 'Complete the assignment'})
    goal_id = client.get('/api/goals').get_json()[0]['id']
    client.patch(f'/api/goals/{goal_id}', json={'completed': True})
    response = client.get('/api/goals/completed')
    assert response.status_code == 200
    assert len(response.get_json()) > 0
