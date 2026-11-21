CREATE TABLE state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    root TEXT NOT NULL,
    revision INTEGER NOT NULL
);
INSERT INTO state VALUES (1, '', 0);

CREATE TABLE files (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL CHECK (size >= 0),
    modified_ns INTEGER NOT NULL,
    indexed INTEGER NOT NULL
);
CREATE INDEX file_path_nocase ON files(path COLLATE NOCASE);
CREATE VIRTUAL TABLE content_search USING fts5(
    body, subwords, content='', contentless_delete=1, tokenize='porter unicode61'
);

CREATE TABLE chunks (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    file_rowid INTEGER NOT NULL REFERENCES files(rowid),
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL
);
CREATE INDEX chunks_by_file ON chunks(file_rowid);
CREATE VIRTUAL TABLE chunk_search USING fts5(
    name, signature, documentation, body, subwords,
    content='', contentless_delete=1, tokenize='porter unicode61'
);
