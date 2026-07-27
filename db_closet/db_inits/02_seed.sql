---


-- ==========================================
-- 1. SEED USERS
-- ==========================================
-- Role mapping: 4 = Admin, 3 = Livreur, 2 = Sourceur, 1 = Cliente
-- Requirements:
-- - 1 Admin (role 4)
-- - 3 Livreurs (role 3)
-- - 2 Sourceurs (role 2) -> also needed in suppliers table
-- - 2 Clientas (role 1)

INSERT INTO users (user_id, email, hash_password, phone, full_name, role, city) 
VALUES
-- Role 4 (Admin - Only 1)
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'admin@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 20 12 34 56', 'Admin Principal', 4, 'Douala'),

-- Role 3 (Livreurs - 3 users)
    ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'livreur1@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 50 23 45 67', 'Jean Livreur', 3, 'Douala'),
    ('b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'livreur2@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 70 34 56 78', 'Paul Transport', 3, 'Yaoundé'),

-- Role 2 (Sourceurs - 2 users, linked to suppliers table)
    ('c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'sourceur1@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 21 56 78 90', 'Alice NDOUNGUE', 2, 'Douala'),
    ('c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'sourceur2@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 51 67 89 01', 'Bobby MBOMBA', 2, 'Yaoundé'),
    ('b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'sourceur3@thrift.cm', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 90 45 67 89', 'Marie NGOMBE', 2, 'Douala'),

-- Role 1 (Clientas - 2 users)
    ('d1eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'client1@gmail.com', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 71 78 90 12', 'Chantal OUMAROU', 1, 'Douala'),
    ('d2eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'client2@gmail.com', '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '+237 6 91 89 01 23', 'Diane KAMGA', 1, 'Yaoundé');


-- ==========================================
-- 2. SEED SUPPLIERS
-- ==========================================
-- Requirement: 2 of the role2 users mapped here.

INSERT INTO public.suppliers (supplier_id, validated, collab_type, supplier_since) 
VALUES
    ('c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', TRUE, 'VENTE DIRECT', NOW() - INTERVAL '30 days'),
    ('c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', TRUE, 'DEPÔT VENTE', NOW() - INTERVAL '15 days');


-- ==========================================
-- 3. SEED ITEMS
-- ==========================================
-- Requirement: 7 items related to role 2 users (suppliers)

INSERT INTO public.items (item_id, supplier_id, universe, house, item_state, price, story, size, item_status) 
VALUES
    ('ITM00001', 'c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Vetement', 'Zara', 'NEUF', 25000.00, 'Robe d’été élégante achetée à Paris.', 38, 'EN_VENTE'),
    ('ITM00002', 'c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Chaussure', 'Nike', 'TRES_BON', 45000.00, 'Sneakers portées deux fois.', 42, 'EN_VENTE'),
    ('ITM00003', 'c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Maison', 'Ikea', 'BON', 15000.00, 'Lampe de chevet vintage.', 0, 'EN_VERIFICATION'),
    ('ITM00004', 'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Vetement', 'Levi''s', 'TRES_BON', 30000.00, 'Jean Levi''s denim authentique.', 40, 'EN_VENTE'),
    ('ITM00005', 'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Accessoire', 'Gucci', 'BON', 120000.00, 'Sac à main de seconde main en cuir.', NULL, 'EN_VENTE'),
    ('ITM00006', 'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Vetement', 'Adidas', 'NEUF', 35000.00, 'Survêtement jamais porté avec étiquette.', 36, 'SOUMIS'),
    ('ITM00007', 'c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'Maison', 'Zara', 'TRES_BON', 18000.00, 'Ceinture en cuir naturel.', NULL, 'EN_VENTE');


-- ==========================================
-- 4. SEED SELECTIONS (Orders/Carts)
-- ==========================================
-- Requirement: 2 selections for each of the role1 users (Clientas)

INSERT INTO public.selections (selection_id, client_id, selection_status, qty, total_selection, delivering_fee, total_amount, delivery_address, delivery_date) 
VALUES
-- Client 1 selections
    ('SEL-1001', 'd1eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'CONFIRMEE', 1, 25000.00, 2000.00, 27000.00, 'Akwa, Douala', NOW() + INTERVAL '2 days'),
    ('SEL-1002', 'd1eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'PAYEE', 1, 45000.00, 2000.00, 47000.00, 'Akwa, Douala', NOW() + INTERVAL '1 day'),

-- Client 2 selections
    ('SEL-2001', 'd2eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'CONFIRMEE', 1, 30000.00, 25000.00, 55000.00, 'Bastos, Yaoundé', NOW() + INTERVAL '3 days'),
    ('SEL-2002', 'd2eebc99-9c0b-4ef8-bb6d-6bb9bd380a44', 'LIVREE', 1, 120000.00, 3000.00, 123000.00, 'Bastos, Yaoundé', NOW() - INTERVAL '1 day');


-- ==========================================
-- 5. SEED ORDER_ITEM (Linking Selections to Items)
-- ==========================================

INSERT INTO public.order_item (selection_id, item_id) VALUES
('SEL-1001', 'ITM00001'),
('SEL-1002', 'ITM00002'),
('SEL-2001', 'ITM00004'),
('SEL-2002', 'ITM00005');
