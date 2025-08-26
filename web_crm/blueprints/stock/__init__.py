from flask import Blueprint

stock_bp = Blueprint('stock', __name__)

from . import routes