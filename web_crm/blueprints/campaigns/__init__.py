from flask import Blueprint

campaigns_bp = Blueprint('campaigns', __name__)

from . import routes