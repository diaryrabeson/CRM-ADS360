from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import campaigns_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime
import json

@campaigns_bp.route('/')
@login_required
@permission_required('campaigns', 'read')
def index():
    """Liste des campagnes"""
    print("DEBUG - g.user structure:", dict(g.user))
    print("DEBUG - g.user keys:", list(g.user.keys()))
    
    # Essayer différentes clés possibles pour le rôle
    user_role = (
        g.user.get('role_name') or 
        g.user.get('role') or 
        g.user.get('role_name') or
        (g.user.get('permissions') and 'partner' if 'sites' in g.user.get('permissions', {}) else None)
    )
    
    print(f"DEBUG - Extracted user_role: {user_role}")
    
    # Si toujours None, utiliser une valeur par défaut basée sur les permissions
    if not user_role:
        if g.user.get('permissions') and 'all' in g.user.get('permissions', {}):
            user_role = 'admin'
        elif g.user.get('permissions') and 'sites' in g.user.get('permissions', {}):
            user_role = 'partner'
        else:
            user_role = 'client'
    
    print(f"DEBUG - Final user_role: {user_role}")
    
    if user_role == 'client':
        campaigns = execute_query(""" 
            SELECT c.*, e.name as client_name,
                   COUNT(DISTINCT s.id) as sites_count
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            LEFT JOIN campaign_revenue_distribution crd ON c.id = crd.campaign_id
            LEFT JOIN sites s ON crd.entity_id = s.entity_id
            WHERE c.client_id = %s
            GROUP BY c.id, e.name
            ORDER BY c.created_at DESC
        """, (g.user['entity_id'],), fetch_all=True)
    elif user_role == 'partner':
        # Partenaire ne voit que les campagnes où il a des revenus
        campaigns = execute_query("""
            SELECT c.*, e.name as client_name,
                   crd.amount as partner_revenue,
                   crd.site_count,
                   crd.status as revenue_status
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            JOIN campaign_revenue_distribution crd ON c.id = crd.campaign_id
            WHERE crd.entity_id = %s
            ORDER BY c.created_at DESC
        """, (g.user['entity_id'],), fetch_all=True)
    else:
        campaigns = execute_query("""
            SELECT c.*, e.name as client_name,
                   COUNT(DISTINCT crd.entity_id) as partners_count
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            LEFT JOIN campaign_revenue_distribution crd ON c.id = crd.campaign_id
            GROUP BY c.id, e.name
            ORDER BY c.created_at DESC
        """, fetch_all=True)
    
    # Statistiques - différentes selon le rôle
    if user_role == 'partner':
        stats = {
            'active': execute_query("""
                SELECT COUNT(DISTINCT c.id) as count 
                FROM campaigns c
                JOIN campaign_revenue_distribution crd ON c.id = crd.campaign_id
                WHERE crd.entity_id = %s AND c.status = 'active'
            """, (g.user['entity_id'],), fetch_one=True)['count'],
            'total_budget': execute_query("""
                SELECT COALESCE(SUM(crd.amount), 0) as total 
                FROM campaign_revenue_distribution crd
                WHERE crd.entity_id = %s AND crd.status = 'paid'
            """, (g.user['entity_id'],), fetch_one=True)['total'],
            'completed': execute_query("""
                SELECT COUNT(DISTINCT c.id) as count 
                FROM campaigns c
                JOIN campaign_revenue_distribution crd ON c.id = crd.campaign_id
                WHERE crd.entity_id = %s AND c.status = 'completed'
            """, (g.user['entity_id'],), fetch_one=True)['count']
        }
    else:
        stats = {
            'active': execute_query("SELECT COUNT(*) as count FROM campaigns WHERE status = 'active'", fetch_one=True)['count'],
            'total_budget': execute_query("SELECT COALESCE(SUM(budget), 0) as total FROM campaigns WHERE status = 'active'", fetch_one=True)['total'],
            'completed': execute_query("SELECT COUNT(*) as count FROM campaigns WHERE status = 'completed'", fetch_one=True)['count']
        }
    
    # Charger les clients seulement pour les admins
    clients = []
    if user_role not in ['client', 'partner']:
        clients = execute_query("""
            SELECT id, name FROM entities 
            WHERE type = 'client'
            ORDER BY name
        """, fetch_all=True)
    
    return render_template('campaigns/index.html', 
                         campaigns=campaigns, 
                         stats=stats,
                         clients=clients,
                         role=user_role)


@campaigns_bp.route('/create', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def create():
    """Créer une nouvelle campagne (JSON seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON manquantes'}), 400
        
        budget = float(data.get('budget', 0))
        admin_share = budget * 0.7
        partners_share = budget * 0.3
        
        # DEBUG: Afficher la structure de g.user pour comprendre
        print("DEBUG - g.user structure:", dict(g.user))
        
        # Déterminer le client_id - utiliser get() pour éviter KeyError
        user_role = g.user.get('role_name') or g.user.get('role')
        if user_role == 'client':
            client_id = g.user.get('entity_id')
        else:
            client_id = data.get('client_id')
            if not client_id:
                return jsonify({'success': False, 'error': 'Client requis'}), 400
        
        # Validation des champs obligatoires
        required_fields = ['name', 'start_date', 'end_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Le champ {field} est obligatoire'}), 400
        
        # Créer la campagne
        campaign_id = execute_query("""
            INSERT INTO campaigns (
                name, client_id, budget, admin_share, partners_share,
                start_date, end_date, status, creative_assets, targeting, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('name'),
            client_id,
            budget,
            admin_share,
            partners_share,
            data.get('start_date'),
            data.get('end_date'),
            'draft',
            json.dumps(data.get('creative_assets', [])),
            json.dumps(data.get('targeting', {})),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        # Calculer la répartition pour les partenaires
        partners_sites = execute_query("""
            SELECT e.id as entity_id, COUNT(s.id) as site_count
            FROM entities e
            JOIN sites s ON e.id = s.entity_id
            WHERE e.type = 'partner' AND s.is_active = TRUE
            GROUP BY e.id
        """, fetch_all=True)
        
        total_sites = sum(p['site_count'] for p in partners_sites)
        
        if total_sites > 0:
            for partner in partners_sites:
                percentage = (partner['site_count'] / total_sites) * 100
                amount = partners_share * (percentage / 100)
                
                execute_query("""
                    INSERT INTO campaign_revenue_distribution (
                        campaign_id, entity_id, site_count, percentage, amount
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    campaign_id,
                    partner['entity_id'],
                    partner['site_count'],
                    percentage,
                    amount
                ), commit=True)
        
        # Ajouter la part admin
        admin_entity = execute_query("SELECT id FROM entities WHERE type = 'admin' LIMIT 1", fetch_one=True)
        if admin_entity:
            execute_query("""
                INSERT INTO campaign_revenue_distribution (
                    campaign_id, entity_id, site_count, percentage, amount
                ) VALUES (%s, %s, 0, 70, %s)
            """, (campaign_id, admin_entity['id'], admin_share), commit=True)
        
        return jsonify({'success': True, 'id': campaign_id})
        
    except Exception as e:
        print(f"Error creating campaign: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@campaigns_bp.route('/api/clients')
@login_required
@permission_required('campaigns', 'read')
def get_clients():
    """Récupérer la liste des clients"""
    clients = execute_query("""
        SELECT id, name FROM entities 
        WHERE type = 'client'
        ORDER BY name
    """, fetch_all=True)
    
    return jsonify(clients)


@campaigns_bp.route('/api/<int:campaign_id>')
@login_required
@permission_required('campaigns', 'read')
def api_campaign_detail(campaign_id):
    """API pour récupérer les détails d'une campagne (JSON)"""
    user_role = g.user.get('role_name') or g.user.get('role')
    
    # Vérifier si le partenaire a accès à cette campagne
    if user_role == 'partner':
        has_access = execute_query("""
            SELECT 1 FROM campaign_revenue_distribution 
            WHERE campaign_id = %s AND entity_id = %s
        """, (campaign_id, g.user['entity_id']), fetch_one=True)
        
        if not has_access:
            return jsonify({'error': 'Accès non autorisé'}), 403
    
    campaign = execute_query("""
        SELECT c.*, e.name as client_name, 
               u.first_name || ' ' || u.last_name as created_by_name
        FROM campaigns c
        LEFT JOIN entities e ON c.client_id = e.id
        LEFT JOIN users u ON c.created_by = u.id
        WHERE c.id = %s
    """, (campaign_id,), fetch_one=True)
    
    if not campaign:
        return jsonify({'error': 'Campagne introuvable'}), 404
    
    # Répartition des revenus - filtrer pour les partenaires
    if user_role == 'partner':
        revenue_distribution = execute_query("""
            SELECT crd.*, e.name as entity_name
            FROM campaign_revenue_distribution crd
            JOIN entities e ON crd.entity_id = e.id
            WHERE crd.campaign_id = %s AND crd.entity_id = %s
            ORDER BY crd.amount DESC
        """, (campaign_id, g.user['entity_id']), fetch_all=True)
    else:
        revenue_distribution = execute_query("""
            SELECT crd.*, e.name as entity_name
            FROM campaign_revenue_distribution crd
            JOIN entities e ON crd.entity_id = e.id
            WHERE crd.campaign_id = %s
            ORDER BY crd.amount DESC
        """, (campaign_id,), fetch_all=True)
    
    # Sites concernés - filtrer pour les partenaires
    if user_role == 'partner':
        sites = execute_query("""
            SELECT s.*, cities.name as city_name, e.name as entity_name
            FROM sites s
            JOIN cities ON s.city_id = cities.geonameid
            JOIN entities e ON s.entity_id = e.id
            WHERE s.entity_id = %s AND e.id IN (
                SELECT entity_id FROM campaign_revenue_distribution 
                WHERE campaign_id = %s
            )
        """, (g.user['entity_id'], campaign_id), fetch_all=True)
    else:
        sites = execute_query("""
            SELECT s.*, cities.name as city_name, e.name as entity_name
            FROM sites s
            JOIN cities ON s.city_id = cities.geonameid
            JOIN entities e ON s.entity_id = e.id
            WHERE e.id IN (
                SELECT entity_id FROM campaign_revenue_distribution 
                WHERE campaign_id = %s AND entity_id != (
                    SELECT id FROM entities WHERE type = 'admin' LIMIT 1
                )
            )
        """, (campaign_id,), fetch_all=True)
    
    return jsonify({
        'campaign': campaign,
        'revenue_distribution': revenue_distribution,
        'sites': sites
    })

@campaigns_bp.route('/api/<int:campaign_id>/upload-proof', methods=['POST'])
@login_required
@permission_required('campaigns', 'read')  # Les partenaires ont read permission
def upload_campaign_proof(campaign_id):
    """Uploader des preuves de diffusion pour une campagne (partenaires seulement)"""
    try:
        user_role = g.user.get('role_name') or g.user.get('role')
        
        # Vérifier que c'est un partenaire et qu'il a accès à cette campagne
        if user_role != 'partner':
            return jsonify({'error': 'Accès réservé aux partenaires'}), 403
        
        # Vérifier l'accès à la campagne
        has_access = execute_query("""
            SELECT 1 FROM campaign_revenue_distribution 
            WHERE campaign_id = %s AND entity_id = %s
        """, (campaign_id, g.user['entity_id']), fetch_one=True)
        
        if not has_access:
            return jsonify({'error': 'Accès non autorisé à cette campagne'}), 403
        
        # Récupérer les fichiers
        if 'proof_images' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400
        
        files = request.files.getlist('proof_images')
        site_id = request.form.get('site_id')
        
        if not site_id:
            return jsonify({'error': 'Site ID requis'}), 400
        
        # Vérifier que le site appartient au partenaire
        site_belongs = execute_query("""
            SELECT 1 FROM sites 
            WHERE id = %s AND entity_id = %s
        """, (site_id, g.user['entity_id']), fetch_one=True)
        
        if not site_belongs:
            return jsonify({'error': 'Site non autorisé'}), 403
        
        # Traiter les fichiers (à adapter selon votre système de stockage)
        uploaded_files = []
        for file in files:
            if file.filename == '':
                continue
            
            # Ici vous devriez sauvegarder le fichier et stocker le chemin
            # Exemple simplifié :
            filename = f"campaign_{campaign_id}_site_{site_id}_{file.filename}"
            # file.save(os.path.join('uploads', filename))
            
            uploaded_files.append({
                'filename': filename,
                'original_name': file.filename,
                'upload_date': datetime.now().isoformat()
            })
        
        # Enregistrer dans la base de données
        execute_query("""
            INSERT INTO campaign_proofs 
            (campaign_id, site_id, partner_id, proof_data, uploaded_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            campaign_id,
            site_id,
            g.user['entity_id'],
            json.dumps(uploaded_files),
            g.user['id']
        ), commit=True)
        
        return jsonify({'success': True, 'message': 'Preuves uploadées avec succès'})
        
    except Exception as e:
        print(f"Error uploading proof: {str(e)}")
        return jsonify({'error': str(e)}), 500
    

@campaigns_bp.route('/api/<int:campaign_id>/partner-sites')
@login_required
@permission_required('campaigns', 'read')
def get_partner_sites(campaign_id):
    """Récupérer les sites du partenaire pour une campagne spécifique"""
    user_role = g.user.get('role_name') or g.user.get('role')
    
    if user_role != 'partner':
        return jsonify({'error': 'Accès réservé aux partenaires'}), 403
    
    # Vérifier l'accès à la campagne
    has_access = execute_query("""
        SELECT 1 FROM campaign_revenue_distribution 
        WHERE campaign_id = %s AND entity_id = %s
    """, (campaign_id, g.user['entity_id']), fetch_one=True)
    
    if not has_access:
        return jsonify({'error': 'Accès non autorisé'}), 403
    
    # Récupérer les sites du partenaire pour cette campagne
    sites = execute_query("""
        SELECT s.id, s.name, cities.name as city_name
        FROM sites s
        JOIN cities ON s.city_id = cities.geonameid
        WHERE s.entity_id = %s AND s.id IN (
            SELECT site_id FROM campaign_sites WHERE campaign_id = %s
        )
    """, (g.user['entity_id'], campaign_id), fetch_all=True)
    
    return jsonify(sites)

@campaigns_bp.route('/<int:campaign_id>/activate', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def activate_campaign(campaign_id):
    """Activer une campagne"""
    try:
        execute_query("""
            UPDATE campaigns SET status = 'active' WHERE id = %s
        """, (campaign_id,), commit=True)
        
        return jsonify({'success': True, 'message': 'Campagne activée avec succès'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@campaigns_bp.route('/<int:campaign_id>/pause', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def pause_campaign(campaign_id):
    """Mettre une campagne en pause"""
    try:
        execute_query("""
            UPDATE campaigns SET status = 'paused' WHERE id = %s
        """, (campaign_id,), commit=True)
        
        return jsonify({'success': True, 'message': 'Campagne mise en pause avec succès'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@campaigns_bp.route('/<int:campaign_id>/complete', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def complete_campaign(campaign_id):
    """Marquer une campagne comme terminée"""
    try:
        execute_query("""
            UPDATE campaigns SET status = 'completed' WHERE id = %s
        """, (campaign_id,), commit=True)
        
        return jsonify({'success': True, 'message': 'Campagne terminée avec succès'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@campaigns_bp.route('/<int:campaign_id>/resume', methods=['POST'])
@login_required
@permission_required('campaigns', 'update')
def resume_campaign(campaign_id):
    """Reprendre une campagne mise en pause"""
    # Vérifier que la campagne existe et est en pause
    campaign = execute_query("SELECT status FROM campaigns WHERE id = %s", (campaign_id,), fetch_one=True)
    if not campaign:
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    
    if campaign['status'] != 'paused':
        return jsonify({'success': False, 'error': 'Seules les campagnes en pause peuvent être reprises'}), 400
    
    # Mise à jour du statut
    execute_query(
        "UPDATE campaigns SET status = %s, updated_at = %s WHERE id = %s",
        ('active', datetime.utcnow(), campaign_id),
        commit=True
    )
    
    return jsonify({'success': True, 'message': 'Campagne reprise avec succès'})

@campaigns_bp.route('/<int:campaign_id>/delete', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def delete_campaign(campaign_id):
    """Supprimer une campagne"""
    try:
        # Vérifier que l'utilisateur a le droit de supprimer
        campaign = execute_query("SELECT * FROM campaigns WHERE id = %s", (campaign_id,), fetch_one=True)
        
        if not campaign:
            return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
            
        # Les clients ne peuvent supprimer que leurs propres campagnes
        user_role = g.user.get('role_name') or g.user.get('role')
        if user_role == 'client' and campaign['client_id'] != g.user['entity_id']:
            return jsonify({'success': False, 'error': 'Accès non autorisé'}), 403
        
        # Supprimer d'abord les distributions de revenus
        execute_query("DELETE FROM campaign_revenue_distribution WHERE campaign_id = %s", (campaign_id,), commit=True)
        
        # Supprimer les preuves
        execute_query("DELETE FROM campaign_proofs WHERE campaign_id = %s", (campaign_id,), commit=True)
        
        # Supprimer la campagne
        execute_query("DELETE FROM campaigns WHERE id = %s", (campaign_id,), commit=True)
        
        return jsonify({'success': True, 'message': 'Campagne supprimée avec succès'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@campaigns_bp.route('/<int:campaign_id>/payment-info')
@login_required
@permission_required('campaigns', 'read')
def campaign_payment_info(campaign_id):
    """Récupérer les informations de paiement d'une campagne"""
    try:
        campaign = execute_query("""
            SELECT c.*, e.name as client_name
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            WHERE c.id = %s
        """, (campaign_id,), fetch_one=True)
        
        if not campaign:
            return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
        
        revenue_distribution = execute_query("""
            SELECT crd.*, e.name as entity_name
            FROM campaign_revenue_distribution crd
            JOIN entities e ON crd.entity_id = e.id
            WHERE crd.campaign_id = %s
            ORDER BY e.name
        """, (campaign_id,), fetch_all=True)
        
        return jsonify({
            'success': True,
            'campaign': campaign,
            'revenue_distribution': revenue_distribution
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@campaigns_bp.route('/revenue/<int:revenue_id>/mark-paid', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
@permission_required('finance', 'write')
def mark_revenue_paid(revenue_id):
    """Marquer une distribution de revenu comme payée, créer une facture et enregistrer le paiement"""
    try:
        # Récupérer les informations de la distribution de revenu
        revenue = execute_query("""
            SELECT crd.*, c.name as campaign_name, e.name as partner_name
            FROM campaign_revenue_distribution crd
            JOIN campaigns c ON crd.campaign_id = c.id
            JOIN entities e ON crd.entity_id = e.id
            WHERE crd.id = %s
        """, (revenue_id,), fetch_one=True)
        
        if not revenue:
            return jsonify({'success': False, 'error': 'Distribution de revenu introuvable'}), 404
        
        # Marquer comme payé
        execute_query("""
            UPDATE campaign_revenue_distribution 
            SET status = 'paid', paid_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (revenue_id,), commit=True)
        
        # Créer une facture dans le module finance
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{revenue_id}"
        amount_float = float(revenue['amount'])
        
        invoice = execute_query("""
            INSERT INTO invoices (
                invoice_number, client_id, amount, tax_amount, total_amount,
                due_date, status, items, created_by, paid_amount
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, total_amount, paid_amount
        """, (
            invoice_number,
            revenue['entity_id'],
            amount_float,
            0,
            amount_float,
            datetime.now().date(),
            'paid',
            json.dumps([{
                'description': f"Paiement campagne: {revenue['campaign_name']}",
                'quantity': 1,
                'unit_price': amount_float,
                'total': amount_float
            }]),
            g.user['id'],
            amount_float  # payé immédiatement
        ), fetch_one=True, commit=True)
        
        invoice_id = invoice['id']
        
        # Enregistrer le paiement lié
        execute_query("""
            INSERT INTO payments (
                invoice_id, amount, payment_date, payment_method,
                reference, recorded_by
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            invoice_id,
            amount_float,
            datetime.now().date(),
            'transfer',
            f"Paiement campagne #{revenue['campaign_id']}",
            g.user['id']
        ), commit=True)
        
        return jsonify({
            'success': True,
            'message': 'Paiement marqué comme effectué et facture créée',
            'invoice_id': invoice_id,
            'invoice_status': 'paid'
        })
    except Exception as e:
        print(f"Error in mark_revenue_paid: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500



@campaigns_bp.route('/<int:campaign_id>/mark-all-paid', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
@permission_required('finance', 'write')
def mark_all_paid(campaign_id):
    """Marquer tous les paiements d'une campagne comme effectués, créer les factures et les paiements"""
    try:
        # Récupérer toutes les distributions non payées
        revenues = execute_query("""
            SELECT crd.*, e.name as partner_name, c.name as campaign_name
            FROM campaign_revenue_distribution crd
            JOIN entities e ON crd.entity_id = e.id
            JOIN campaigns c ON crd.campaign_id = c.id
            WHERE crd.campaign_id = %s AND crd.status != 'paid'
        """, (campaign_id,), fetch_all=True)
        
        created_invoices = []

        for revenue in revenues:
            amount_float = float(revenue['amount'])
            
            # Marquer comme payé
            execute_query("""
                UPDATE campaign_revenue_distribution 
                SET status = 'paid', paid_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (revenue['id'],), commit=True)
            
            # Créer la facture
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{revenue['id']}"
            
            invoice = execute_query("""
                INSERT INTO invoices (
                    invoice_number, client_id, amount, tax_amount, total_amount,
                    due_date, status, items, created_by, paid_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, total_amount, paid_amount
            """, (
                invoice_number,
                revenue['entity_id'],
                amount_float,
                0,
                amount_float,
                datetime.now().date(),
                'paid',
                json.dumps([{
                    'description': f"Paiement campagne: {revenue['campaign_name']}",
                    'quantity': 1,
                    'unit_price': amount_float,
                    'total': amount_float
                }]),
                g.user['id'],
                amount_float
            ), fetch_one=True, commit=True)

            invoice_id = invoice['id']
            created_invoices.append(invoice_id)

            # Enregistrer le paiement lié
            execute_query("""
                INSERT INTO payments (
                    invoice_id, amount, payment_date, payment_method,
                    reference, recorded_by
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                invoice_id,
                amount_float,
                datetime.now().date(),
                'transfer',
                f"Paiement campagne #{campaign_id}",
                g.user['id']
            ), commit=True)
        
        return jsonify({
            'success': True,
            'message': f"Tous les paiements ont été marqués comme effectués ({len(revenues)} factures créées)",
            'invoices': created_invoices
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@campaigns_bp.route('/<int:campaign_id>/stats')
@login_required
@permission_required('campaigns', 'read')
def campaign_stats(campaign_id):
    """Récupérer les statistiques détaillées d'une campagne"""
    try:
        # Statistiques de base
        campaign = execute_query("""
            SELECT c.*, e.name as client_name,
                   u.first_name || ' ' || u.last_name as created_by_name
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            LEFT JOIN users u ON c.created_by = u.id
            WHERE c.id = %s
        """, (campaign_id,), fetch_one=True)
        
        if not campaign:
            return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
        
        # Répartition des revenus
        revenue_distribution = execute_query("""
            SELECT crd.*, e.name as entity_name,
                   COUNT(cp.id) as proof_count
            FROM campaign_revenue_distribution crd
            JOIN entities e ON crd.entity_id = e.id
            LEFT JOIN campaign_proofs cp ON crd.campaign_id = cp.campaign_id 
                AND crd.entity_id = cp.partner_id
            WHERE crd.campaign_id = %s
            GROUP BY crd.id, e.name
            ORDER BY crd.amount DESC
        """, (campaign_id,), fetch_all=True)
        
        # Preuves de diffusion
        proofs = execute_query("""
            SELECT cp.*, s.name as site_name, 
                   u.first_name || ' ' || u.last_name as uploaded_by_name
            FROM campaign_proofs cp
            LEFT JOIN sites s ON cp.site_id = s.id
            LEFT JOIN users u ON cp.uploaded_by = u.id
            WHERE cp.campaign_id = %s
            ORDER BY cp.upload_date DESC
        """, (campaign_id,), fetch_all=True)
        
        # Statistiques financières
        financial_stats = execute_query("""
            SELECT 
                COUNT(*) as total_distributions,
                COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_distributions,
                SUM(amount) as total_amount,
                SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) as paid_amount,
                SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END) as pending_amount
            FROM campaign_revenue_distribution
            WHERE campaign_id = %s
        """, (campaign_id,), fetch_one=True)
        
        return jsonify({
            'success': True,
            'campaign': campaign,
            'revenue_distribution': revenue_distribution,
            'proofs': proofs,
            'financial_stats': financial_stats
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@campaigns_bp.route('/update-payments', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def update_payments():
    """Mettre à jour les statuts de paiement"""
    try:
        data = request.get_json()
        
        for update in data.get('updates', []):
            # CORRECTION: utiliser paid_at au lieu de payment_date
            execute_query("""
                UPDATE campaign_revenue_distribution 
                SET status = %s, 
                    paid_at = CASE WHEN %s = 'paid' THEN CURRENT_TIMESTAMP ELSE paid_at END
                WHERE id = %s
            """, (update['status'], update['status'], update['revenue_id']), commit=True)
        
        return jsonify({'success': True, 'message': 'Statuts de paiement mis à jour'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@campaigns_bp.route('/<int:campaign_id>/proofs')
@login_required
@permission_required('campaigns', 'read')
def list_proofs(campaign_id):
    """Lister toutes les preuves d'une campagne (admin only)"""
    user_role = g.user.get('role_name') or g.user.get('role')

    if user_role != 'super_admin':
        return jsonify({'error': 'Accès réservé aux admins'}), 403

    proofs = execute_query("""
        SELECT cp.*, s.name as site_name, e.name as partner_name, u.first_name || ' ' || u.last_name as uploaded_by_name
        FROM campaign_proofs cp
        JOIN sites s ON cp.site_id = s.id
        JOIN entities e ON cp.partner_id = e.id
        LEFT JOIN users u ON cp.uploaded_by = u.id
        WHERE cp.campaign_id = %s
        ORDER BY cp.upload_date DESC
    """, (campaign_id,), fetch_all=True)

    return jsonify(proofs)

@campaigns_bp.route('/proofs/<int:proof_id>/validate', methods=['POST'])
@login_required
@permission_required('campaigns', 'write')
def validate_proof(proof_id):
    """Valider ou rejeter une preuve (admin only)"""
    user_role = g.user.get('role_name') or g.user.get('role')
    if user_role != 'super_admin':
        return jsonify({'error': 'Accès réservé aux admins'}), 403

    data = request.get_json()
    status = data.get('status')
    if status not in ['approved', 'rejected']:
        return jsonify({'error': 'Status invalide'}), 400

    execute_query("""
        UPDATE campaign_proofs
        SET status = %s
        WHERE id = %s
    """, (status, proof_id), commit=True)

    return jsonify({'success': True, 'message': f'Preuve {status}'})

@campaigns_bp.route('/proofs/<int:proof_id>')
@login_required
@permission_required('super_admin', 'read')
def get_proof(proof_id):
    proof = execute_query("""
        SELECT p.id, p.filename, 
            '/uploads/' || p.filename as url,  -- construit l'URL
            p.mime_type, p.size, p.width, p.height, p.duration, p.upload_date,
            u.first_name || ' ' || u.last_name as uploaded_by_name
        FROM proofs p
        LEFT JOIN users u ON u.id = p.uploaded_by
        WHERE p.id = %s

    """, (proof_id,), fetch_one=True)

    if not proof:
        return jsonify({"error": "Preuve introuvable"}), 404

    return jsonify(proof)
