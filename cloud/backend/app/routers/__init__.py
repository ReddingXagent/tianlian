# Auto-generated routing initialization for settlement_bills API
from flask import Blueprint
settlement_bp = Blueprint('settlement', __name__,
                      url_prefix='/fleet/settlement')

# Import route handlers
from .bills import fetch_bills, update_bill_status, get_bill_details