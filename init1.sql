CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users(
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR UNIQUE,
    hash_password VARCHAR,
    phone VARCHAR UNIQUE,
    full_name VARCHAR,
    role INT, -- 4 = Admin, 3 = Livreur, 2 = Sourceur, 1 = Cliente
    created_at TIMESTAMP,
    city VARCHAR,


    CONSTRAINT check_email_format CHECK (email LIKE '_%@_%._%'),
    CONSTRAINT check_role CHECK (role IN (1,2,3,4))

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
    status VARCHAR,

    FOREIGN KEY (supplier_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_price CHECK (price > 0.0),
    CONSTRAINT check_state CHECK (item_state IN ('NEUF',  'TRES_BON', 'BON')),
    CONSTRAINT check_status CHECK (status IN ('SOUMIS', 'EN_VERIFICATION', 'ACCEPTE', 'REFUSE', 'VENDU', 'EN_VENTE'))
);

CREATE TABLE IF NOT EXISTS selections(
    selection_id VARCHAR PRIMARY KEY,
    client_id UUID,
    order_date TIMESTAMP NOT NULL,
    order_status VARCHAR,
    total_selection FLOAT,
    delivering_fee FLOAT,
    code_promo VARCHAR,
    total_amount FLOAT,
    guest_token VARCHAR,
    delivery_address VARCHAR,
    delivery_date TIMESTAMP,
    
    FOREIGN KEY (client_id) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT check_total_selection CHECK (total_selection > 0.00),
    CONSTRAINT check_total_amount CHECK (total_amount > 0.00),
    CONSTRAINT check_status CHECK (order_status IN ('ANNULEE', 'CONFIRMEE', 'PAYEE', 'PREPAREE', 'LIVREE'))

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
    supplier_since DATE,
    collab_type VARCHAR NOT NULL,

    CONSTRAINT check_collab_type CHECK (collab_type IN ('VENTE DIRECT', 'DEPOT VENTE'))
);

CREATE TABLE IF NOT EXISTS wishlist(
    client_id UUID NOT NULL,
    item_id VARCHAR NOT NULL,
    added_at TIMESTAMP,

    PRIMARY KEY(client_id, item_id),
    FOREIGN KEY(client_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE

);

CREATE INDEX IX_user_email ON users(email) ;
CREATE INDEX IX_user_phone ON users(phone); 
