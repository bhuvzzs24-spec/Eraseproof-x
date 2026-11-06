CREATE SCHEMA customer;
CREATE SCHEMA orders;
CREATE SCHEMA delivery;
CREATE SCHEMA analytics;
CREATE TABLE customer.customers (
 id uuid PRIMARY KEY, name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 email text NOT NULL UNIQUE CHECK(email ~ '^[a-zA-Z0-9._+-]+@example[.]invalid$'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE orders.orders (
 id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customer.customers(id) ON DELETE RESTRICT,
 amount_cents integer NOT NULL CHECK(amount_cents > 0), currency text NOT NULL CHECK(currency IN ('USD','INR','EUR')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orders_customer_idx ON orders.orders(customer_id);
CREATE TABLE delivery.outbox (
 id uuid PRIMARY KEY, aggregate_id uuid NOT NULL, event_type text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz, attempts integer NOT NULL DEFAULT 0, last_error text,
 next_attempt_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_pending_idx ON delivery.outbox(next_attempt_at) WHERE published_at IS NULL;
CREATE INDEX outbox_aggregate_idx ON delivery.outbox(aggregate_id);
CREATE TABLE delivery.processed (
 consumer text NOT NULL, event_id uuid NOT NULL, customer_id uuid NOT NULL,
 processed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(consumer,event_id)
);
CREATE INDEX processed_customer_idx ON delivery.processed(customer_id);
CREATE TABLE analytics.events (
 event_id uuid PRIMARY KEY, customer_id uuid NOT NULL, event_type text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analytics_customer_idx ON analytics.events(customer_id);
