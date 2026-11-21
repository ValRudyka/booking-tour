-- =====================================================================
-- 02. Schema: 27 tables, keys, constraints, indexes (revision 7b9314761125)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app"
-- (so tour_app owns the tables). Open Query Tool -> paste/open file -> F5.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 7b9314761125

CREATE TABLE countries (
    id SERIAL NOT NULL, 
    iso_code VARCHAR(2) NOT NULL, 
    name_uk VARCHAR(100) NOT NULL, 
    name_en VARCHAR(100), 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_countries PRIMARY KEY (id), 
    CONSTRAINT uq_countries_iso_code UNIQUE (iso_code)
);

CREATE TABLE insurance_types (
    id SERIAL NOT NULL, 
    name_uk VARCHAR(100) NOT NULL, 
    price_uah NUMERIC(12, 2) NOT NULL, 
    is_default BOOLEAN DEFAULT 'false' NOT NULL, 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_insurance_types PRIMARY KEY (id)
);

CREATE TABLE languages (
    code VARCHAR(5) NOT NULL, 
    name VARCHAR(50) NOT NULL, 
    is_enabled BOOLEAN DEFAULT 'true' NOT NULL, 
    CONSTRAINT pk_languages PRIMARY KEY (code)
);

CREATE TABLE transfer_types (
    id SERIAL NOT NULL, 
    name_uk VARCHAR(100) NOT NULL, 
    price_uah NUMERIC(12, 2) NOT NULL, 
    is_default BOOLEAN DEFAULT 'false' NOT NULL, 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_transfer_types PRIMARY KEY (id)
);

CREATE TABLE cities (
    id SERIAL NOT NULL, 
    country_id INTEGER NOT NULL, 
    name_uk VARCHAR(100) NOT NULL, 
    name_en VARCHAR(100), 
    iata_code VARCHAR(3), 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_cities PRIMARY KEY (id), 
    CONSTRAINT fk_cities_country_id_countries FOREIGN KEY(country_id) REFERENCES countries (id)
);

CREATE INDEX ix_cities_country_id ON cities (country_id);

CREATE TABLE resorts (
    id SERIAL NOT NULL, 
    country_id INTEGER NOT NULL, 
    name_uk VARCHAR(100) NOT NULL, 
    name_en VARCHAR(100), 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_resorts PRIMARY KEY (id), 
    CONSTRAINT fk_resorts_country_id_countries FOREIGN KEY(country_id) REFERENCES countries (id)
);

CREATE INDEX ix_resorts_country_id ON resorts (country_id);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    phone VARCHAR(20) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(32) DEFAULT 'client' NOT NULL, 
    last_name VARCHAR(100) NOT NULL, 
    first_name VARCHAR(100) NOT NULL, 
    birth_date DATE, 
    citizenship_id INTEGER, 
    consent_at TIMESTAMP WITH TIME ZONE, 
    loyalty_points INTEGER DEFAULT '0' NOT NULL, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT ck_users_loyalty_points_non_negative CHECK (loyalty_points >= 0), 
    CONSTRAINT fk_users_citizenship_id_countries FOREIGN KEY(citizenship_id) REFERENCES countries (id), 
    CONSTRAINT uq_users_email UNIQUE (email), 
    CONSTRAINT uq_users_phone UNIQUE (phone), 
    CONSTRAINT ck_users_user_role CHECK (role IN ('client', 'manager', 'finance', 'admin'))
);

CREATE INDEX ix_users_role ON users (role);

CREATE TABLE audit_log (
    id SERIAL NOT NULL, 
    user_id INTEGER, 
    entity VARCHAR(50) NOT NULL, 
    entity_id VARCHAR(50) NOT NULL, 
    action VARCHAR(50) NOT NULL, 
    old_value JSONB, 
    new_value JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_audit_log PRIMARY KEY (id), 
    CONSTRAINT fk_audit_log_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_log_user_id ON audit_log (user_id);

CREATE TABLE currency_rates (
    currency VARCHAR(32) NOT NULL, 
    rate_to_uah NUMERIC(12, 4) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_by INTEGER, 
    CONSTRAINT pk_currency_rates PRIMARY KEY (currency), 
    CONSTRAINT ck_currency_rates_rate_positive CHECK (rate_to_uah > 0), 
    CONSTRAINT fk_currency_rates_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id), 
    CONSTRAINT ck_currency_rates_currency CHECK (currency IN ('UAH', 'EUR', 'USD'))
);

CREATE TABLE hotels (
    id SERIAL NOT NULL, 
    resort_id INTEGER NOT NULL, 
    name VARCHAR(150) NOT NULL, 
    stars SMALLINT, 
    description TEXT, 
    rating_avg NUMERIC(3, 2), 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    CONSTRAINT pk_hotels PRIMARY KEY (id), 
    CONSTRAINT ck_hotels_stars_range CHECK (stars BETWEEN 1 AND 5), 
    CONSTRAINT fk_hotels_resort_id_resorts FOREIGN KEY(resort_id) REFERENCES resorts (id)
);

CREATE INDEX ix_hotels_resort_id ON hotels (resort_id);

CREATE TABLE promo_codes (
    id SERIAL NOT NULL, 
    code VARCHAR(20) NOT NULL, 
    discount_type VARCHAR(32) NOT NULL, 
    discount_value NUMERIC(12, 2) NOT NULL, 
    min_order_uah NUMERIC(12, 2), 
    valid_from DATE NOT NULL, 
    valid_to DATE NOT NULL, 
    usage_limit INTEGER, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    created_by INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_promo_codes PRIMARY KEY (id), 
    CONSTRAINT ck_promo_codes_percent_max_100 CHECK (discount_type = 'fixed' OR discount_value <= 100), 
    CONSTRAINT ck_promo_codes_discount_positive CHECK (discount_value > 0), 
    CONSTRAINT ck_promo_codes_usage_limit_positive CHECK (usage_limit IS NULL OR usage_limit > 0), 
    CONSTRAINT ck_promo_codes_validity_order CHECK (valid_to >= valid_from), 
    CONSTRAINT fk_promo_codes_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT uq_promo_codes_code UNIQUE (code), 
    CONSTRAINT ck_promo_codes_discount_type CHECK (discount_type IN ('percent', 'fixed'))
);

CREATE TABLE saved_passports (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    last_name_lat VARCHAR(100) NOT NULL, 
    first_name_lat VARCHAR(100) NOT NULL, 
    passport_number VARCHAR(20) NOT NULL, 
    issuing_authority VARCHAR(4), 
    expiry_date DATE NOT NULL, 
    CONSTRAINT pk_saved_passports PRIMARY KEY (id), 
    CONSTRAINT fk_saved_passports_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_saved_passports_user_id ON saved_passports (user_id);

CREATE TABLE search_history (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    params JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_search_history PRIMARY KEY (id), 
    CONSTRAINT fk_search_history_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_search_history_user_id ON search_history (user_id);

CREATE TABLE settings (
    key VARCHAR(50) NOT NULL, 
    value JSONB NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_by INTEGER, 
    CONSTRAINT pk_settings PRIMARY KEY (key), 
    CONSTRAINT fk_settings_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id)
);

CREATE TABLE tours (
    id SERIAL NOT NULL, 
    title_uk VARCHAR(200) NOT NULL, 
    title_en VARCHAR(200) NOT NULL, 
    hotel_id INTEGER NOT NULL, 
    transport_type VARCHAR(32) NOT NULL, 
    departure_city_id INTEGER, 
    flight_out VARCHAR(10), 
    flight_back VARCHAR(10), 
    departure_from DATE NOT NULL, 
    departure_to DATE NOT NULL, 
    nights SMALLINT NOT NULL, 
    seats_total INTEGER NOT NULL, 
    seats_sold INTEGER DEFAULT '0' NOT NULL, 
    base_price NUMERIC(12, 2) NOT NULL, 
    child_price NUMERIC(12, 2), 
    currency VARCHAR(32) NOT NULL, 
    description TEXT, 
    is_featured BOOLEAN DEFAULT 'false' NOT NULL, 
    status VARCHAR(32) DEFAULT 'draft' NOT NULL, 
    created_by INTEGER NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_tours PRIMARY KEY (id), 
    CONSTRAINT ck_tours_departure_city_required CHECK (transport_type = 'none' OR departure_city_id IS NOT NULL), 
    CONSTRAINT ck_tours_base_price_positive CHECK (base_price > 0), 
    CONSTRAINT ck_tours_child_price_non_negative CHECK (child_price IS NULL OR child_price >= 0), 
    CONSTRAINT ck_tours_departure_dates_order CHECK (departure_to >= departure_from), 
    CONSTRAINT ck_tours_nights_range CHECK (nights BETWEEN 1 AND 30), 
    CONSTRAINT ck_tours_seats_within_quota CHECK (seats_sold >= 0 AND seats_sold <= seats_total), 
    CONSTRAINT fk_tours_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_tours_departure_city_id_cities FOREIGN KEY(departure_city_id) REFERENCES cities (id), 
    CONSTRAINT fk_tours_hotel_id_hotels FOREIGN KEY(hotel_id) REFERENCES hotels (id), 
    CONSTRAINT ck_tours_transport_type CHECK (transport_type IN ('air', 'bus', 'none')), 
    CONSTRAINT ck_tours_currency CHECK (currency IN ('UAH', 'EUR', 'USD')), 
    CONSTRAINT ck_tours_tour_status CHECK (status IN ('draft', 'active', 'archived'))
);

CREATE INDEX ix_tours_departure_from ON tours (departure_from);

CREATE INDEX ix_tours_hotel_id ON tours (hotel_id);

CREATE INDEX ix_tours_status ON tours (status);

CREATE TABLE favorites (
    user_id INTEGER NOT NULL, 
    tour_id INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_favorites PRIMARY KEY (user_id, tour_id), 
    CONSTRAINT fk_favorites_tour_id_tours FOREIGN KEY(tour_id) REFERENCES tours (id) ON DELETE CASCADE, 
    CONSTRAINT fk_favorites_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE orders (
    id SERIAL NOT NULL, 
    number VARCHAR(20) NOT NULL, 
    client_id INTEGER NOT NULL, 
    tour_id INTEGER NOT NULL, 
    manager_id INTEGER, 
    status VARCHAR(32) DEFAULT 'checkout' NOT NULL, 
    payment_status VARCHAR(32) DEFAULT 'awaiting' NOT NULL, 
    start_date DATE NOT NULL, 
    end_date DATE NOT NULL, 
    adults SMALLINT NOT NULL, 
    children SMALLINT DEFAULT '0' NOT NULL, 
    insurance_type_id INTEGER, 
    transfer_type_id INTEGER, 
    promo_code_id INTEGER, 
    wishes TEXT, 
    total_uah NUMERIC(12, 2) NOT NULL, 
    discount_uah NUMERIC(12, 2) DEFAULT '0' NOT NULL, 
    rate_used NUMERIC(12, 4) NOT NULL, 
    hold_expires_at TIMESTAMP WITH TIME ZONE, 
    pnr VARCHAR(20), 
    operator_deadline DATE, 
    internal_comment TEXT, 
    reject_reason TEXT, 
    cancel_reason TEXT, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_orders PRIMARY KEY (id), 
    CONSTRAINT ck_orders_at_least_one_adult CHECK (adults >= 1), 
    CONSTRAINT ck_orders_children_non_negative CHECK (children >= 0), 
    CONSTRAINT ck_orders_dates_order CHECK (end_date > start_date), 
    CONSTRAINT ck_orders_total_non_negative CHECK (total_uah >= 0), 
    CONSTRAINT fk_orders_client_id_users FOREIGN KEY(client_id) REFERENCES users (id), 
    CONSTRAINT fk_orders_insurance_type_id_insurance_types FOREIGN KEY(insurance_type_id) REFERENCES insurance_types (id), 
    CONSTRAINT fk_orders_manager_id_users FOREIGN KEY(manager_id) REFERENCES users (id), 
    CONSTRAINT fk_orders_promo_code_id_promo_codes FOREIGN KEY(promo_code_id) REFERENCES promo_codes (id), 
    CONSTRAINT fk_orders_tour_id_tours FOREIGN KEY(tour_id) REFERENCES tours (id), 
    CONSTRAINT fk_orders_transfer_type_id_transfer_types FOREIGN KEY(transfer_type_id) REFERENCES transfer_types (id), 
    CONSTRAINT uq_orders_number UNIQUE (number), 
    CONSTRAINT ck_orders_order_status CHECK (status IN ('checkout', 'awaiting_payment', 'paid', 'in_progress', 'confirmed', 'documents_ready', 'completed', 'rejected', 'cancel_requested', 'cancelled', 'archived')), 
    CONSTRAINT ck_orders_payment_status CHECK (payment_status IN ('awaiting', 'partially_paid', 'paid', 'partially_refunded', 'refunded'))
);

CREATE INDEX ix_orders_client_id ON orders (client_id);

CREATE INDEX ix_orders_manager_id ON orders (manager_id);

CREATE INDEX ix_orders_status ON orders (status);

CREATE INDEX ix_orders_tour_id ON orders (tour_id);

CREATE TABLE tour_images (
    id SERIAL NOT NULL, 
    tour_id INTEGER NOT NULL, 
    file_path VARCHAR(300) NOT NULL, 
    sort_order SMALLINT DEFAULT '0' NOT NULL, 
    CONSTRAINT pk_tour_images PRIMARY KEY (id), 
    CONSTRAINT fk_tour_images_tour_id_tours FOREIGN KEY(tour_id) REFERENCES tours (id) ON DELETE CASCADE
);

CREATE INDEX ix_tour_images_tour_id ON tour_images (tour_id);

CREATE TABLE tour_program_days (
    id SERIAL NOT NULL, 
    tour_id INTEGER NOT NULL, 
    day_number SMALLINT NOT NULL, 
    description TEXT NOT NULL, 
    CONSTRAINT pk_tour_program_days PRIMARY KEY (id), 
    CONSTRAINT fk_tour_program_days_tour_id_tours FOREIGN KEY(tour_id) REFERENCES tours (id) ON DELETE CASCADE
);

CREATE INDEX ix_tour_program_days_tour_id ON tour_program_days (tour_id);

CREATE TABLE loyalty_transactions (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    order_id INTEGER, 
    points INTEGER NOT NULL, 
    reason VARCHAR(200) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_loyalty_transactions PRIMARY KEY (id), 
    CONSTRAINT fk_loyalty_transactions_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL, 
    CONSTRAINT fk_loyalty_transactions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_loyalty_transactions_user_id ON loyalty_transactions (user_id);

CREATE TABLE notifications (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    order_id INTEGER, 
    title VARCHAR(200) NOT NULL, 
    body TEXT NOT NULL, 
    is_read BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notifications PRIMARY KEY (id), 
    CONSTRAINT fk_notifications_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE SET NULL, 
    CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE order_documents (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    doc_type VARCHAR(32) NOT NULL, 
    file_path VARCHAR(300) NOT NULL, 
    uploaded_by INTEGER NOT NULL, 
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_order_documents PRIMARY KEY (id), 
    CONSTRAINT fk_order_documents_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE, 
    CONSTRAINT fk_order_documents_uploaded_by_users FOREIGN KEY(uploaded_by) REFERENCES users (id), 
    CONSTRAINT ck_order_documents_order_document_type CHECK (doc_type IN ('voucher', 'air_ticket', 'insurance_policy', 'info_sheet'))
);

CREATE INDEX ix_order_documents_order_id ON order_documents (order_id);

CREATE TABLE order_status_history (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    old_status VARCHAR(32), 
    new_status VARCHAR(32) NOT NULL, 
    changed_by INTEGER, 
    comment TEXT, 
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_order_status_history PRIMARY KEY (id), 
    CONSTRAINT fk_order_status_history_changed_by_users FOREIGN KEY(changed_by) REFERENCES users (id), 
    CONSTRAINT fk_order_status_history_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE
);

CREATE INDEX ix_order_status_history_order_id ON order_status_history (order_id);

CREATE TABLE order_tourists (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    last_name_lat VARCHAR(100) NOT NULL, 
    first_name_lat VARCHAR(100) NOT NULL, 
    birth_date DATE NOT NULL, 
    passport_number VARCHAR(20) NOT NULL, 
    passport_expiry DATE NOT NULL, 
    CONSTRAINT pk_order_tourists PRIMARY KEY (id), 
    CONSTRAINT fk_order_tourists_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE
);

CREATE INDEX ix_order_tourists_order_id ON order_tourists (order_id);

CREATE TABLE payments (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    type VARCHAR(32) NOT NULL, 
    method VARCHAR(32) NOT NULL, 
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    amount_uah NUMERIC(12, 2) NOT NULL, 
    paid_amount NUMERIC(12, 2), 
    currency VARCHAR(32) DEFAULT 'UAH' NOT NULL, 
    purpose VARCHAR(300), 
    received_at TIMESTAMP WITH TIME ZONE, 
    bank_statement_path VARCHAR(300), 
    controller_comment TEXT, 
    stripe_session_id VARCHAR(255), 
    stripe_payment_intent VARCHAR(255), 
    stripe_refund_id VARCHAR(255), 
    confirmed_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_payments PRIMARY KEY (id), 
    CONSTRAINT ck_payments_amount_positive CHECK (amount_uah > 0), 
    CONSTRAINT fk_payments_confirmed_by_users FOREIGN KEY(confirmed_by) REFERENCES users (id), 
    CONSTRAINT fk_payments_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id), 
    CONSTRAINT uq_payments_stripe_session_id UNIQUE (stripe_session_id), 
    CONSTRAINT ck_payments_payment_type CHECK (type IN ('payment', 'refund')), 
    CONSTRAINT ck_payments_payment_method CHECK (method IN ('card', 'bank_transfer')), 
    CONSTRAINT ck_payments_transaction_status CHECK (status IN ('pending', 'succeeded', 'failed')), 
    CONSTRAINT ck_payments_currency CHECK (currency IN ('UAH', 'EUR', 'USD'))
);

CREATE INDEX ix_payments_order_id ON payments (order_id);

CREATE TABLE reviews (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    tour_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    hotel_rating SMALLINT NOT NULL, 
    service_rating SMALLINT NOT NULL, 
    positive TEXT, 
    negative TEXT, 
    name_display VARCHAR(32) DEFAULT 'short' NOT NULL, 
    is_published BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_reviews PRIMARY KEY (id), 
    CONSTRAINT ck_reviews_hotel_rating_range CHECK (hotel_rating BETWEEN 1 AND 5), 
    CONSTRAINT ck_reviews_service_rating_range CHECK (service_rating BETWEEN 1 AND 5), 
    CONSTRAINT fk_reviews_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id), 
    CONSTRAINT fk_reviews_tour_id_tours FOREIGN KEY(tour_id) REFERENCES tours (id), 
    CONSTRAINT fk_reviews_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
    CONSTRAINT uq_reviews_order_id UNIQUE (order_id), 
    CONSTRAINT ck_reviews_name_display CHECK (name_display IN ('full', 'short', 'anonymous'))
);

CREATE INDEX ix_reviews_tour_id ON reviews (tour_id);

CREATE INDEX ix_reviews_user_id ON reviews (user_id);

CREATE TABLE review_photos (
    id SERIAL NOT NULL, 
    review_id INTEGER NOT NULL, 
    file_path VARCHAR(300) NOT NULL, 
    CONSTRAINT pk_review_photos PRIMARY KEY (id), 
    CONSTRAINT fk_review_photos_review_id_reviews FOREIGN KEY(review_id) REFERENCES reviews (id) ON DELETE CASCADE
);

CREATE INDEX ix_review_photos_review_id ON review_photos (review_id);

INSERT INTO alembic_version (version_num) VALUES ('7b9314761125') RETURNING alembic_version.version_num;

COMMIT;

