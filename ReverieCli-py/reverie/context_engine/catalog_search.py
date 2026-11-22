"""The existing lexical ranking contract on Python's portable SQLite FTS layout."""

import math


_CONTENT_QUERY = (
    "SELECT d.rowid,d.path,NULL,NULL,NULL,NULL,bm25(content_search,1.0,0.35) "
    "FROM content_search JOIN content_documents d ON d.rowid=content_search.rowid "
    "WHERE content_search MATCH ? ORDER BY bm25(content_search,1.0,0.35), "
    "d.path COLLATE NOCASE,d.rowid LIMIT ?"
)
_CHUNK_QUERY = (
    "SELECT d.rowid,d.path,d.symbol,d.kind,d.start_line,d.end_line, "
    "bm25(chunk_search,5.5,3.0,1.8,1.0,0.6) "
    "FROM chunk_search JOIN chunk_documents d ON d.rowid=chunk_search.rowid "
    "WHERE chunk_search MATCH ? ORDER BY bm25(chunk_search,5.5,3.0,1.8,1.0,0.6), "
    "d.path COLLATE NOCASE,d.start_line,d.symbol COLLATE NOCASE,d.rowid LIMIT ?"
)


def phrase(term):
    return '"' + term.replace('"', '""') + '"'


def ranked(connection, weights, limit, chunks):
    limit = int(limit)
    if limit <= 0:
        raise ValueError("Limit must be positive")
    normalized = {}
    for term, weight in weights:
        term, weight = str(term or "").strip().lower(), float(weight or 0.0)
        if term and math.isfinite(weight):
            normalized[term] = max(normalized.get(term, 0.0), weight)
    cap, minimum, maximum = (18, 32, 120) if chunks else (16, 24, 96)
    terms = sorted(normalized.items(), key=lambda pair: (-pair[1], pair[0]))[:cap]
    matches = {}
    for term, weight in terms:
        rows = connection.execute(_CHUNK_QUERY if chunks else _CONTENT_QUERY,
                                  (phrase(term), max(minimum, min(maximum, limit * 2))))
        for rank, row in enumerate(rows, 1):
            rowid, path, symbol, kind, start, end, relevance = row
            score = weight * math.log1p(max(0.0, -relevance)) / math.sqrt(rank)
            if chunks and term in symbol.lower():
                score *= 1.25
            if score <= 0.0:
                continue
            if rowid not in matches:
                hit = {"file_path": path, "score": 0.0}
                if chunks:
                    hit.update(symbol=symbol, kind=kind, start_line=start, end_line=end)
                matches[rowid] = (hit, {})
            hit, contributions = matches[rowid]
            hit["score"] += score
            contributions[term] = score
    results = []
    for rowid, (hit, contributions) in matches.items():
        if chunks:
            hit["score"] *= 1.0 + min(0.36, max(0, len(contributions) - 1) * 0.09)
        hit["terms"] = [term for term, _ in sorted(contributions.items(),
                                                  key=lambda pair: (-pair[1], pair[0]))[:8 if chunks else 6]]
        results.append((hit, rowid))
    results.sort(key=lambda pair: (-pair[0]["score"], pair[0]["file_path"].lower(),
                                   pair[0].get("start_line", 0), pair[1]))
    for hit, _ in results[:limit]:
        hit["score"] = round(hit["score"], 4)
    return [hit for hit, _ in results[:limit]]


def frequencies(connection, terms):
    result = {}
    for term in terms:
        term = str(term or "").strip().lower()
        if term and term not in result:
            result[term] = connection.execute(
                "SELECT COUNT(*) FROM content_search WHERE content_search MATCH ?",
                ("body : " + phrase(term),),
            ).fetchone()[0]
    return result


def total(connection):
    return connection.execute("SELECT COUNT(*) FROM content_documents").fetchone()[0]


def paths(connection, prefix, limit):
    if int(limit) <= 0:
        raise ValueError("Limit must be positive")
    prefix = str(prefix).replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
    rows = connection.execute("SELECT path FROM files WHERE path LIKE ? ESCAPE '\\' "
                              "ORDER BY path COLLATE NOCASE,path LIMIT ?", (prefix + "%", int(limit)))
    return [row[0] for row in rows]
