from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import utils_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required

@utils_bp.route('/status_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_status_prospect():
    """Page de recuperation des status du prospect"""
    return jsonify({'status': 'success', 'data': []})

@utils_bp.route('/type_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_prospect():
    """Page de recuperation des types du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/source_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_source_prospect():
    """Page de recuperation des sources du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/category_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_category_prospect():
    """Page de recuperation des categories du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/type_partenariat_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_partenariat_prospect():
    """Page de recuperation des types de partenariat du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/type_relance_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_relance_prospect():
    """Page de recuperation des types de relance du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/type_relance_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_relance_prospect():
    """Page de recuperation des types de relance du prospect"""
    return jsonify({'status': 'success', 'data': []})


@utils_bp.route('/type_equipment', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_relance_prospect():
    """Page de recuperation des types de relance du prospect"""
    return jsonify({'status': 'success', 'data': []})

@utils_bp.route('/type_relance_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_relance_prospect():
    """Page de recuperation des types de relance du prospect"""
    return jsonify({'status': 'success', 'data': []})

@utils_bp.route('/type_relance_prospects', methods=['GET'])
@login_required
@permission_required('utils', 'read')
def utils_type_relance_prospect():
    """Page de recuperation des types de relance du prospect"""
    return jsonify({'status': 'success', 'data': []})