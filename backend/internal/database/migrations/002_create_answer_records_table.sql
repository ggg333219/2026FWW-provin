-- SQL script to create answer_records table
CREATE TABLE IF NOT EXISTS answer_records (
    id SERIAL PRIMARY KEY,
    answer_text TEXT NOT NULL,
    question_id INT NOT NULL,
    user_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);