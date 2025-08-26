import bcrypt

def hash_password(password):
    """Hache un mot de passe"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Vérifie un mot de passe"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
