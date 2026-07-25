CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users(
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR UNIQUE,
    hash_password VARCHAR,
    phone VARCHAR UNIQUE,
    full_name VARCHAR,
    role INT, -- 4 = Admin, 3 = Livreur, 2 = Sourceur, 1 = Cliente
    city VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,

    CONSTRAINT check_email_format CHECK (email LIKE '_%@_%._%'),
    CONSTRAINT check_role CHECK (role IN (1,2,3,4)),
    CONSTRAINT contact_not_null CHECK (email IS NOT NULL OR phone IS NOT NULL)

);

CREATE TABLE IF NOT EXISTS items(
    item_id VARCHAR(8) PRIMARY KEY,
    supplier_id UUID,
    universe VARCHAR NOT NULL,
    house VARCHAR NOT NULL,
    item_state VARCHAR,
    price FLOAT,
    story VARCHAR,
    size INT,
    item_status VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,

    FOREIGN KEY (supplier_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_price CHECK (price > 0.0),
    CONSTRAINT check_state CHECK (item_state IN ('NEUF',  'TRES_BON', 'BON')),
    CONSTRAINT check_item_status CHECK (item_status IN ('SOUMIS', 'EN_VERIFICATION', 'ACCEPTE', 'REFUSE', 'VENDU', 'EN_VENTE'))
);

CREATE TABLE IF NOT EXISTS selections(
    selection_id VARCHAR PRIMARY KEY,
    client_id UUID,
    selection_status VARCHAR DEFAULT 'CONFIRMEE',
    qty INT NOT NULL,
    total_selection FLOAT,
    delivering_fee FLOAT,
    code_promo VARCHAR,
    total_amount FLOAT,
    guest_token VARCHAR,
    delivery_address VARCHAR,
    delivery_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    
    FOREIGN KEY (client_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_qty CHECK (qty > 0),
    CONSTRAINT check_total_selection CHECK (total_selection > 0.00),
    CONSTRAINT check_total_amount CHECK (total_amount > 0.00),
    CONSTRAINT check_selection_status CHECK (selection_status IN ('ANNULEE', 'CONFIRMEE', 'PAYEE', 'PREPAREE', 'LIVREE'))

);

CREATE TABLE IF NOT EXISTS order_item(
    selection_id VARCHAR NOT NULL,
    item_id VARCHAR NOT NULL,

    PRIMARY KEY(selection_id, item_id),
    FOREIGN KEY(selection_id) REFERENCES selections(selection_id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE

);

CREATE TABLE IF NOT EXISTS suppliers(
    supplier_id UUID PRIMARY KEY,
    validated BOOLEAN,
    request_datetime TIMESTAMP DEFAULT NOW(),
    collab_type VARCHAR NOT NULL,
    supplier_since TIMESTAMP,
    updated_at TIMESTAMP,

    CONSTRAINT check_collab_type CHECK (collab_type IN ('VENTE DIRECT', 'DEPÔT VENTE'))
);

CREATE TABLE IF NOT EXISTS favorites(
    client_id UUID NOT NULL,
    item_id VARCHAR NOT NULL,
    added_at TIMESTAMP,

    PRIMARY KEY(client_id, item_id),
    FOREIGN KEY(client_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE

);

CREATE TABLE IF NOT EXISTS notifications(
    notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    recipient_contact VARCHAR NOT NULL,
    channel INT,
    TEMPLATE VARCHAR,
    db_infos JSON,
    notif_status VARCHAR DEFAULT 'EN ATTENTE',
    created_at TIMESTAMP DEFAULT NOW(),
    error_message TEXT,
    updated_at TIMESTAMP,

    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_notif_status CHECK (notif_status IN ('EN ATTENTE','ENVOYEE', 'RECUE', 'ECHEC DE L ENVOI', 'LUE') )
);

CREATE TABLE IF NOT EXISTS deliveries(
    delivery_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    selection_id VARCHAR NOT NULL,
    delivery_agent UUID,
    delivery_status VARCHAR DEFAULT 'PRISE EN CHARGE',
    access_token VARCHAR DEFAULT gen_random_uuid(),
    token_expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,

    FOREIGN KEY(selection_id) REFERENCES selections(selection_id) ON DELETE CASCADE,
    FOREIGN KEY(delivery_agent) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_delivery_status CHECK (delivery_status IN ('PRISE EN CHARGE', 'EN COURS', 'LIVRE', 'ECHOUEE') )
);

CREATE TABLE IF NOT EXISTS pickups(
    pickup_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supplier_id UUID NOT NULL,
    pickup_agent UUID,
    item_id VARCHAR NOT NULL,
    pickup_address VARCHAR NOT NULL,
    additional_indications TEXT,
    pickup_date TIMESTAMP,
    pickup_status VARCHAR DEFAULT 'DEMANDE',
    requested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,

    FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
    FOREIGN KEY(pickup_agent) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE SET NULL,    
    CONSTRAINT chk_pickup_status CHECK (pickup_status IN ('DEMANDE', 'ASSIGNE', 'TERMINE', 'ANNULE') )
);