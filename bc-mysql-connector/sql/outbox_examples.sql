-- How Pretech's own applications send changes to Business Central.
-- Write a row; the connector picks it up on its next cycle and records the outcome.

-- New customer (BC assigns the number; bc_outbox.bc_id and bc_number are filled in after the push)
INSERT INTO bc_outbox (entity, operation, payload, status, attempts)
VALUES ('customers', 'create',
        JSON_OBJECT('displayName', 'Bhima Biotech LLP', 'city', 'Pune', 'country', 'IN', 'currencyCode', 'INR'),
        'pending', 0);

-- Update an item price by its BC number (the connector finds the record id and ETag in bc_items)
INSERT INTO bc_outbox (entity, operation, bc_number, payload, status, attempts)
VALUES ('items', 'update', 'EP-MCC', JSON_OBJECT('unitPrice', 949000), 'pending', 0);

-- Anything that needs a person: validation or permission errors from BC
SELECT id, entity, operation, bc_number, attempts, last_error FROM bc_outbox WHERE status = 'failed';

-- Retry a failed row after fixing its payload
UPDATE bc_outbox SET status = 'pending', attempts = 0, last_error = NULL WHERE id = 42;

-- Reporting straight from the mirror: open sales orders with customer city
SELECT so.number, so.order_date, so.customer_name, c.city, so.total_incl_tax
FROM bc_sales_orders so JOIN bc_customers c ON c.id = so.customer_id
WHERE so.status = 'Open' ORDER BY so.order_date DESC;
