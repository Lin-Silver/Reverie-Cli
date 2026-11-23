CREATE TABLE symbol_references (
    rowid INTEGER PRIMARY KEY,
    file_rowid INTEGER NOT NULL REFERENCES files(rowid),
    source_symbol TEXT NOT NULL,
    target_text TEXT NOT NULL,
    target_symbol TEXT,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    resolution TEXT NOT NULL DEFAULT 'unresolved',
    UNIQUE(file_rowid, source_symbol, target_text, kind, line)
);
CREATE INDEX references_from ON symbol_references(source_symbol);
CREATE INDEX references_to ON symbol_references(target_symbol);
CREATE INDEX references_by_file ON symbol_references(file_rowid);
CREATE INDEX chunks_by_symbol ON chunks(symbol);
