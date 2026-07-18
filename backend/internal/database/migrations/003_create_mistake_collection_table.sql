-- Migration script to create mistake_collection table

CREATE TABLE IF NOT EXISTS mistake_collection (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    mistake_type VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add any additional constraints or indices if necessary