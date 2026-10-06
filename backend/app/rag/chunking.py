MAX_DOC_BYTES = 14 * 1024


def chunk_text(text: str) -> list[str]:
    """Split text so each chunk stays under Chroma Cloud's 16 KiB document limit."""
    body = (text or "").strip() or " "
    encoded = body.encode("utf-8")
    if len(encoded) <= MAX_DOC_BYTES:
        return [body]

    chunks: list[str] = []
    current = ""
    for line in body.splitlines() or [body]:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate.encode("utf-8")) > MAX_DOC_BYTES and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    flattened: list[str] = []
    for chunk in chunks:
        raw = chunk.encode("utf-8")
        if len(raw) <= MAX_DOC_BYTES:
            flattened.append(chunk)
            continue
        start = 0
        while start < len(raw):
            piece = raw[start : start + MAX_DOC_BYTES].decode("utf-8", errors="ignore")
            if piece:
                flattened.append(piece)
            start += MAX_DOC_BYTES
    return flattened or [body[:4000]]
