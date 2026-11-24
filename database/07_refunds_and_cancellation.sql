-- =====================================================================
-- 07. Refunds and cancellation requests (revision 8c41e7d2a9b3)
-- Generated from the Alembic migrations in backend/alembic/versions.
-- Do NOT edit by hand: change the models, create a new migration, re-export.
--
-- Run in pgAdmin connected to database "tour_website" AS USER "tour_app", after 06.
-- Adds payments.refund_of_id (+ links existing automatic refunds), unique stripe_refund_id,
-- orders.fpv_uah, orders.cancel_reason_code and the document type 'cancel_evidence'.
-- The whole script runs in one transaction: it either fully succeeds or changes nothing.
-- =====================================================================

BEGIN;

-- Running upgrade 2d155601a7cd -> 8c41e7d2a9b3

ALTER TABLE payments ADD COLUMN refund_of_id INTEGER;

ALTER TABLE payments ADD CONSTRAINT fk_payments_refund_of_id_payments FOREIGN KEY(refund_of_id) REFERENCES payments (id);

CREATE INDEX ix_payments_refund_of_id ON payments (refund_of_id);

ALTER TABLE payments ADD CONSTRAINT ck_payments_refund_of_only_refunds CHECK (type = 'refund' OR refund_of_id IS NULL);

ALTER TABLE payments ADD CONSTRAINT uq_payments_stripe_refund_id UNIQUE (stripe_refund_id);

UPDATE payments AS r SET refund_of_id = p.id
        FROM payments AS p
        WHERE r.type = 'refund' AND r.refund_of_id IS NULL
          AND p.type = 'payment' AND p.order_id = r.order_id
          AND p.stripe_payment_intent IS NOT NULL
          AND p.stripe_payment_intent = r.stripe_payment_intent;

ALTER TABLE orders ADD COLUMN fpv_uah NUMERIC(12, 2);

ALTER TABLE orders ADD CONSTRAINT ck_orders_fpv_non_negative CHECK (fpv_uah IS NULL OR fpv_uah >= 0);

ALTER TABLE orders ADD COLUMN cancel_reason_code VARCHAR(32);

ALTER TABLE orders ADD CONSTRAINT ck_orders_cancel_reason CHECK (cancel_reason_code IN ('illness', 'change_of_plans', 'data_error', 'visa_refusal', 'other'));

ALTER TABLE order_documents DROP CONSTRAINT ck_order_documents_order_document_type;

ALTER TABLE order_documents ADD CONSTRAINT ck_order_documents_order_document_type CHECK (doc_type IN ('voucher', 'air_ticket', 'insurance_policy', 'info_sheet', 'cancel_evidence'));

UPDATE alembic_version SET version_num='8c41e7d2a9b3' WHERE alembic_version.version_num = '2d155601a7cd';

COMMIT;

