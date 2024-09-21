from os import abort
from flask import Blueprint, request, jsonify, abort
from ..models import db, User
from app.auth import authenticate_user  # Import from auth.py
from ..utils import validate_user_access  # Import the shared validation function

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.route('', methods=['POST'])
@authenticate_user  # Ensure only authenticated users can create themselves
def create_user():
    data = request.json

    # Ensure the authenticated user is creating themselves
    authenticated_email = request.user['email']  # Comes from the Google token
    if authenticated_email != data['email']:
        return jsonify({"message": "Unauthorized: You can only create yourself"}), 403

    # Check if the user already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({"message": "User already exists"}), 200

    # Create the user
    user = User(email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created successfully"}), 201

@bp.route('/<email>', methods=['GET'], endpoint='get_user')
@authenticate_user
def get_user(email):
    # Use the shared validation function
    validation_response = validate_user_access(email)
    if validation_response:
        return validation_response

    user = db.session.get(User, email)
    if user is None:
        return jsonify({"message": "User not found", "email": email}), 404
    return jsonify({"email": user.email})

@bp.route('/<email>', methods=['PUT'])
@authenticate_user
def update_user(email):
    # Use the shared validation function
    validation_response = validate_user_access(email)
    if validation_response:
        return validation_response

    user = db.session.get(User, email)
    if user is None:
        return jsonify({"message": "User not found", "email": email}), 404
    data = request.json
    user.email = data['email']
    db.session.commit()
    return jsonify({"message": "User updated successfully"})

@bp.route('/<email>', methods=['DELETE'])
@authenticate_user
def delete_user(email):
    # Use the shared validation function
    validation_response = validate_user_access(email)
    if validation_response:
        return validation_response

    user = db.session.get(User, email)
    if user is None:
        return jsonify({"message": "User not found", "email": email}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"})


@bp.route('', methods=['GET'])
@authenticate_user
def get_users():
    users = User.query.all()
    return jsonify([{"email": user.email} for user in users])
