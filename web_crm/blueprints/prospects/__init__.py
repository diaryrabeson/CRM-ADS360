from flask import Blueprint

prospects_bp = Blueprint('prospects', __name__)

from . import routes