-- Create some basic users for testing purposes
INSERT INTO users(email, hash_password, phone, full_name, role, city)
VALUES
('client1@example.com', sha256('Password_123'), '+237 691 23 45 67', 'Client1 NGONGANG', 1, 'Yaoundé'),
('client2@example.com', sha256('Password_123'), '+237 692 23 45 87', 'Client2 ESSOMBA', 1, 'Douala'),
('client3@example.com', sha256('Password_123'), '+237 693 23 45 67', 'Client3 NGO NDZE', 1, 'Yaoundé'),

('sourceur1@example.com', sha256('Sourceur_123'), '+237 691 23 45 68', 'Sourceur1 KAMGA', 2, 'Douala'),
('sourceur2@example.com', sha256('Sourceur_123'), '+237 692 23 45 68', 'Sourceur2 MBOMBA', 2, 'Yaoundé'),
('jane@example.com', sha256('Sourceur_123'), '+237 699 99 99 99', 'Jane DOE', 2, 'Douala'),


('livreur1@example.com', sha256('Livreur_123'), '+237 691 23 45 69', 'Belo OUMAROU', 3, 'Yaoundé'),
('admin@example.com', sha256('Admin_123'), '+237 691 23 45 70', 'Admin USER', 4, 'Yaoundé');