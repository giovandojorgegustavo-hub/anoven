-- 2026-06-08: RAG support — document_chunks + attachments indexing columns
-- Anthropic API limit: 100 pages/PDF. For PDFs >100 pages we chunk + embed
-- (Gemini embedding-001 @ 768 dim Matryoshka) and retrieve top-k per query.

BEGIN;

ALTER TABLE attachments
  ADD COLUMN IF NOT EXISTS page_count INTEGER,
  ADD COLUMN IF NOT EXISTS is_indexed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    section_title VARCHAR(255),
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (attachment_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_conversation ON document_chunks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chunks_attachment ON document_chunks(attachment_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

COMMIT;
