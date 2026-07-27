CREATE INDEX IX_user_email ON users(email);
CREATE INDEX IX_user_phone ON users(phone); 

-- Triggers on updated_at column

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';
    -- USERS
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_items_updated_at
    BEFORE UPDATE ON items
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_selections_updated_at
    BEFORE UPDATE ON selections
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_suppliers_updated_at
    BEFORE UPDATE ON suppliers
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notifications_updated_at
    BEFORE UPDATE ON notifications
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_deliveries_updated_at
    BEFORE UPDATE ON deliveries
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pickups_updated_at
    BEFORE UPDATE ON pickups
    FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();