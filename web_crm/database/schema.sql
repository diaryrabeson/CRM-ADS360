-- Table des rôles
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des entités/entreprises
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50), -- 'admin', 'partner', 'client'
    logo VARCHAR(255),
    address TEXT,
    phone VARCHAR(50),
    email VARCHAR(255),
    additional_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des utilisateurs
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(50),
    role_id INTEGER REFERENCES roles(id),
    entity_id INTEGER REFERENCES entities(id),
    is_active BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prospects (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    status VARCHAR(50) DEFAULT 'Nouveau',
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    sector VARCHAR(100),
    country VARCHAR(100),
    company_size VARCHAR(50),
    source VARCHAR(100),
    assigned_to INTEGER REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    converted_at TIMESTAMP,
    converted_to VARCHAR(20),
    converted_entity_id INTEGER REFERENCES entities(id)
);


-- Table des relances de prospection
CREATE TABLE IF NOT EXISTS prospect_followups (
    id SERIAL PRIMARY KEY,
    prospect_id INTEGER REFERENCES prospects(id) ON DELETE CASCADE,
    scheduled_date DATE NOT NULL,
    type VARCHAR(50), -- 'email', 'phone', 'meeting'
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'completed', 'cancelled'
    notes TEXT,
    performed_by INTEGER REFERENCES users(id),
    performed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des pays
CREATE TABLE IF NOT EXISTS countries (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(3) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des villes
CREATE TABLE IF NOT EXISTS cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    country_id INTEGER REFERENCES countries(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des sites/zones
CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100), -- 'Transport', 'Hôtel', 'Bar', etc.
    entity_id INTEGER REFERENCES entities(id),
    city_id INTEGER REFERENCES cities(id),
    address TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    opening_hours JSONB, -- {"monday": {"open": "08:00", "close": "18:00"}, ...}
    photos JSONB, -- ["photo1.jpg", "photo2.jpg"]
    capacity INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des équipements
CREATE TABLE IF NOT EXISTS equipment (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100),
    serial_number VARCHAR(100) UNIQUE,
    model VARCHAR(100),
    manufacturer VARCHAR(100),
    purchase_date DATE,
    purchase_price DECIMAL(12,2),
    status VARCHAR(50) DEFAULT 'available', -- 'available', 'installed', 'maintenance', 'retired'
    specifications JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des entrepôts
CREATE TABLE IF NOT EXISTS warehouses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    location TEXT,
    manager_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table du stock
CREATE TABLE IF NOT EXISTS stock (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER REFERENCES equipment(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    quantity INTEGER DEFAULT 0,
    min_quantity INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des mouvements de stock
CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER REFERENCES equipment(id),
    from_type VARCHAR(50), -- 'warehouse' ou 'site'
    from_id INTEGER,
    to_type VARCHAR(50), -- 'warehouse' ou 'site'
    to_id INTEGER,
    quantity INTEGER NOT NULL,
    reason VARCHAR(255),
    performed_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des installations d'équipements sur sites
CREATE TABLE IF NOT EXISTS site_equipment (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id),
    equipment_id INTEGER REFERENCES equipment(id),
    installation_date DATE,
    installed_by INTEGER REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE site_equipment 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Table des campagnes publicitaires
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    client_id INTEGER REFERENCES entities(id),
    budget DECIMAL(12,2) NOT NULL,
    admin_share DECIMAL(12,2), -- 70% du budget
    partners_share DECIMAL(12,2), -- 30% du budget
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'active', 'paused', 'completed'
    creative_assets JSONB, -- Liens vers les créas publicitaires
    targeting JSONB, -- Critères de ciblage
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table de répartition des revenus de campagne
CREATE TABLE IF NOT EXISTS campaign_revenue_distribution (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    entity_id INTEGER REFERENCES entities(id),
    site_count INTEGER,
    percentage DECIMAL(5,2),
    amount DECIMAL(12,2),
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'paid'
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des preuves de diffusion des campagnes
CREATE TABLE IF NOT EXISTS campaign_proofs (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    site_id INTEGER REFERENCES sites(id),
    partner_id INTEGER REFERENCES entities(id),
    proof_data JSONB, -- {"files": [{"filename": "...", "upload_date": "..."}]}
    uploaded_by INTEGER REFERENCES users(id),
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    reviewed_by INTEGER REFERENCES users(id),
    review_date TIMESTAMP,
    review_notes TEXT
);

-- Table des fournisseurs
CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    tax_id VARCHAR(50),
    payment_terms VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des bons de commande
CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    po_number VARCHAR(50) UNIQUE NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    order_date DATE NOT NULL,
    expected_delivery DATE,
    total_amount DECIMAL(12,2),
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'sent', 'received', 'cancelled'
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des lignes de commande
CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id SERIAL PRIMARY KEY,
    purchase_order_id INTEGER REFERENCES purchase_orders(id) ON DELETE CASCADE,
    equipment_name VARCHAR(255),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12,2),
    total_price DECIMAL(12,2),
    received_quantity INTEGER DEFAULT 0,
    warehouse_id INTEGER REFERENCES warehouses(id)
);

-- Table des projets
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    client_id INTEGER REFERENCES entities(id),
    start_date DATE,
    end_date DATE,
    status VARCHAR(50) DEFAULT 'planning', -- 'planning', 'in_progress', 'completed', 'cancelled'
    budget DECIMAL(12,2),
    project_manager_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des tâches de projet
CREATE TABLE IF NOT EXISTS project_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    assigned_to INTEGER REFERENCES users(id),
    site_id INTEGER REFERENCES sites(id),
    start_date DATE,
    end_date DATE,
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'normal',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des employés (RH)
CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    employee_code VARCHAR(50) UNIQUE,
    department VARCHAR(100),
    position VARCHAR(100),
    hire_date DATE NOT NULL,
    contract_type VARCHAR(50), -- 'CDI', 'CDD', 'Stage', etc.
    contract_end_date DATE,
    salary DECIMAL(12,2),
    social_benefits JSONB,
    emergency_contact JSONB,
    documents JSONB, -- Liens vers documents (CV, contrat, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des congés
CREATE TABLE IF NOT EXISTS leaves (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    type VARCHAR(50), -- 'Congé payé', 'Maladie', 'Formation', etc.
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    approved_by INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des présences
CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    date DATE NOT NULL,
    check_in TIME,
    check_out TIME,
    status VARCHAR(50), -- 'present', 'absent', 'late', 'leave'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, date)
);

-- Table des formations
CREATE TABLE IF NOT EXISTS trainings (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(50), -- 'internal', 'external', 'online'
    duration_hours INTEGER,
    cost DECIMAL(10,2),
    provider VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des participations aux formations
CREATE TABLE IF NOT EXISTS employee_trainings (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    training_id INTEGER REFERENCES trainings(id),
    scheduled_date DATE,
    completion_date DATE,
    status VARCHAR(50) DEFAULT 'scheduled',
    score DECIMAL(5,2),
    certificate_url VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des évaluations de performance
CREATE TABLE IF NOT EXISTS performance_reviews (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id),
    reviewer_id INTEGER REFERENCES users(id),
    review_period VARCHAR(50),
    objectives JSONB,
    achievements JSONB,
    overall_rating DECIMAL(3,2),
    comments TEXT,
    next_review_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des devis
CREATE TABLE IF NOT EXISTS quotes (
    id SERIAL PRIMARY KEY,
    quote_number VARCHAR(50) UNIQUE NOT NULL,
    client_id INTEGER REFERENCES entities(id),
    amount DECIMAL(12,2) NOT NULL,
    validity_date DATE,
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'sent', 'accepted', 'rejected', 'expired'
    items JSONB,
    terms TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des factures
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    quote_id INTEGER REFERENCES quotes(id),
    client_id INTEGER REFERENCES entities(id),
    amount DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2),
    total_amount DECIMAL(12,2),
    due_date DATE,
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'sent', 'paid', 'overdue', 'cancelled'
    items JSONB,
    payment_method VARCHAR(50),
    paid_amount DECIMAL(12,2) DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des paiements
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    amount DECIMAL(12,2) NOT NULL,
    payment_date DATE NOT NULL,
    payment_method VARCHAR(50),
    reference VARCHAR(100),
    notes TEXT,
    recorded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des logs d'audit
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id INTEGER,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table des paramètres système
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB,
    description TEXT,
    updated_by INTEGER REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_logins (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    username VARCHAR(255),
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE proofs (
    id SERIAL PRIMARY KEY,
    campaign_id INT NOT NULL,
    site_id INT,
    filename TEXT,
    mime_type TEXT,
    size BIGINT,
    width INT,
    height INT,
    duration INT,
    uploaded_by INT,
    upload_date TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'pending'
);


ALTER TABLE projects ADD COLUMN assigned_to INTEGER REFERENCES users(id);
ALTER TABLE sites ADD COLUMN warehouse_id INTEGER REFERENCES warehouses(id);
ALTER TABLE site_equipment 
ADD COLUMN quantity INTEGER DEFAULT 1,
ADD COLUMN removed_quantity INTEGER DEFAULT 0;
ALTER TABLE stock ADD COLUMN removed_quantity INTEGER DEFAULT 0;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS tax_amount DECIMAL(12,2);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invoice_date DATE;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS due_date DATE;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS payment_terms TEXT;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS sent_date DATE;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS sent_date DATE;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS terms TEXT;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS sent_to VARCHAR(255);
ALTER TABLE invoices 
ADD COLUMN IF NOT EXISTS quote_id INTEGER REFERENCES quotes(id);

-- -------------------------------
-- Table des pays
-- -------------------------------
DROP TABLE IF EXISTS countries CASCADE;

CREATE TABLE countries (
    iso2 VARCHAR(2),
    iso3 VARCHAR(3),
    iso_numeric INT,
    fips VARCHAR(10),
    name VARCHAR(200),
    capital VARCHAR(200),
    area FLOAT,
    population BIGINT,
    continent VARCHAR(10),
    tld VARCHAR(10),
    currency_code VARCHAR(10),
    currency_name VARCHAR(50),
    phone VARCHAR(50),
    postal_code_format VARCHAR(255),
    postal_code_regex VARCHAR(500),
    languages VARCHAR(255),
    geonameid BIGINT,
    neighbours VARCHAR(255),
    extra TEXT
);

-- -------------------------------
-- Table des régions / admin1
-- -------------------------------
DROP TABLE IF EXISTS admin1 CASCADE;

CREATE TABLE admin1 (
    geonameid BIGINT PRIMARY KEY,
    country_code VARCHAR(2),
    code VARCHAR(20),
    name VARCHAR(200),
    ascii_name VARCHAR(200),
    geonameid_parent BIGINT,
    population BIGINT,
    latitude FLOAT,
    longitude FLOAT,
    timezone VARCHAR(50),
    extra TEXT
);

DROP TABLE IF EXISTS tmp_admin1 CASCADE;
-- Créer une table temporaire pour l'import
CREATE TEMP TABLE tmp_admin1 (
    code_full TEXT,
    name TEXT,
    ascii_name TEXT,
    geonameid BIGINT
);

-- -------------------------------
-- Table des villes / cities
-- -------------------------------
DROP TABLE IF EXISTS cities CASCADE;

CREATE TABLE cities (
    geonameid BIGINT PRIMARY KEY,
    name VARCHAR(200),
    ascii_name VARCHAR(200),
    alternate_names TEXT,
    latitude FLOAT,
    longitude FLOAT,
    feature_class VARCHAR(10),
    feature_code VARCHAR(20),
    country_code VARCHAR(2),
    cc2 TEXT,
    admin1_code VARCHAR(20),
    admin2_code VARCHAR(20),
    admin3_code VARCHAR(20),
    admin4_code VARCHAR(20),
    population BIGINT,
    elevation VARCHAR(50),
    dem VARCHAR(50),
    timezone VARCHAR(50),
    modification_date DATE
);





-- Index pour améliorer les performances
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role_id);
CREATE INDEX idx_prospects_status ON prospects(status);
CREATE INDEX idx_prospects_assigned ON prospects(assigned_to);
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_dates ON campaigns(start_date, end_date);
CREATE INDEX idx_sites_entity ON sites(entity_id);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);

-- Insertion des rôles par défaut
INSERT INTO roles (name, description, permissions) VALUES
('super_admin', 'Administrateur système avec tous les droits', '{"all": true}'),
('admin_entity', 'Administrateur d''entité', '{"entity": ["read", "write", "delete"]}'),
('commercial_manager', 'Gestionnaire commercial', '{"prospects": ["read", "write"], "campaigns": ["read", "write"]}'),
('stock_manager', 'Gestionnaire de stock', '{"stock": ["read", "write"], "equipment": ["read", "write"]}'),
('hr_manager', 'Gestionnaire RH', '{"hr": ["read", "write"], "employees": ["read", "write"]}'),
('finance_manager', 'Gestionnaire financier', '{"finance": ["read", "write"], "invoices": ["read", "write"]}'),
('partner', 'Partenaire', '{"sites": ["read"], "campaigns": ["read"]}'),
('client', 'Client', '{"campaigns": ["read", "write"], "invoices": ["read"]}')
ON CONFLICT (name) DO NOTHING;

-- Insertion de l'entité admin par défaut
INSERT INTO entities (name, type, email) VALUES
('Admin ADS 360', 'admin', 'crm@ads360.digital')
ON CONFLICT DO NOTHING;

-- Insertion du super admin par défaut (mot de passe: Admin@123)
INSERT INTO users (email, password_hash, first_name, last_name, role_id, entity_id) 
SELECT 'crm@ads360.digital', '$2b$12$SOAQrefNoT0IYP7YpQw5x.Z5nq1us6xpDB7Z6p1XKtSTCK5uhM/9C', 'Super', 'Admin', 
       (SELECT id FROM roles WHERE name = 'super_admin'),
       (SELECT id FROM entities WHERE type = 'admin' LIMIT 1)
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'crm@ads360.digital');

\COPY cities(
    geonameid, 
    name, 
    ascii_name, 
    alternate_names, 
    latitude, 
    longitude, 
    feature_class, 
    feature_code, 
    country_code, 
    cc2, 
    admin1_code, 
    admin2_code, 
    admin3_code, 
    admin4_code, 
    population, 
    elevation, 
    dem, 
    timezone, 
    modification_date
)
FROM '/home/benounet/Dev_project/CRM-ADS360/web_crm/database/cities500.txt'
WITH (FORMAT text, DELIMITER E'\t', NULL '', ENCODING 'UTF8');

\COPY countries FROM '/home/benounet/Dev_project/CRM-ADS360/web_crm/database/countryInfo.txt' WITH (FORMAT text, DELIMITER E'\t', NULL '', ENCODING 'UTF8');

-- Copier les données brutes dans la table temporaire
\COPY tmp_admin1 FROM '/home/benounet/Dev_project/CRM-ADS360/web_crm/database/admin1CodesASCII.txt' WITH (FORMAT text, DELIMITER E'\t', NULL '', ENCODING 'UTF8');


-- Insérer dans la table admin1 finale
INSERT INTO admin1 (geonameid, country_code, code, name, ascii_name)
SELECT
    geonameid,
    split_part(code_full, '.', 1) AS country_code,
    split_part(code_full, '.', 2) AS code,
    name,
    ascii_name
FROM tmp_admin1;
