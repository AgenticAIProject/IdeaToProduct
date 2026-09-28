from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///goals.db'
db = SQLAlchemy(app)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {"id": self.id, "goal": self.description, "completed": self.completed, "created_at": self.created_at}

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/api/goals', methods=['POST'])
def create_goal():
    data = request.json
    if not data or 'goal' not in data:
        return jsonify({'message': 'Goal description is required.'}), 400
    existing_goal = Goal.query.filter_by(description=data['goal']).first()
    if existing_goal:
        return jsonify({'message': 'Goal already exists.'}), 400
    goal = Goal(description=data['goal'])
    db.session.add(goal)
    db.session.commit()
    return jsonify(goal.as_dict()), 201

@app.route('/api/goals', methods=['GET'])
def get_goals():
    goals = Goal.query.all()
    return jsonify([goal.as_dict() for goal in goals])

@app.route('/api/goals/<int:id>', methods=['DELETE'])
def delete_goal(id):
    goal = Goal.query.get(id)
    if goal is None:
        return jsonify({'message': 'Goal not found.'}), 404
    db.session.delete(goal)
    db.session.commit()
    return '', 204

@app.route('/api/goals/completed', methods=['GET'])
def get_completed_goals():
    completed_goals = Goal.query.filter_by(completed=True).order_by(Goal.created_at.desc()).all()
    return jsonify([goal.as_dict() for goal in completed_goals])

@app.route('/api/goals/<int:id>', methods=['PATCH'])
def update_goal_completion(id):
    goal = Goal.query.get(id)
    if goal is None:
        return jsonify({'message': 'Goal not found.'}), 404
    data = request.json
    if 'completed' in data:
        goal.completed = data['completed']
        db.session.commit()
    return jsonify(goal.as_dict())

if __name__ == '__main__':
    app.run(debug=True)
