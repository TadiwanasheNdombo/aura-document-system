from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, password, role):
        self.id = id
        self.username = username
        self.password = password
        self.role = role

# In-memory user store for demonstration
# In a real application, this would be a database
users = {
    "branch_user": User(id="1", username="branch_user", password="password", role="branch"),
    "cpc_user": User(id="2", username="cpc_user", password="password", role="cpc")
}

def get_user(username):
    return users.get(username)

def get_user_by_id(user_id):
    for user in users.values():
        if user.id == user_id:
            return user
    return None
