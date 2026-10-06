from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


def _page(info: dict) -> str:
    rows = "".join(
        f"""
        <tr>
          <td>{item.get('title','')}</td>
          <td>{item.get('source','')}</td>
          <td>{item.get('city','')}</td>
          <td><a href="{item.get('url','')}" target="_blank">link</a></td>
        </tr>
        """
        for item in info.get("items", [])
    ) or "<tr><td colspan='4'>No vectors stored yet.</td></tr>"
    error = f"<p class='error'>{info.get('error')}</p>" if info.get("error") else ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ChromaDB viewer</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; background: #f6f1e7; color: #223042; margin: 32px; }}
    .card {{ background: white; border-radius: 16px; padding: 24px; max-width: 960px; }}
    h1 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eadfca; }}
    .meta {{ color: #66758a; }}
    .error {{ color: #9b2c2c; }}
    a {{ color: #102033; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>ChromaDB viewer</h1>
    <p class="meta">Mode: {info.get('mode')} · Host: {info.get('host')} · Collection: {info.get('collection', 'listings')} · Records: {info.get('count', 0)}</p>
    <p class="meta">Local Chroma is the on-disk copy. Cloud search is used when it replies within the timeout.{info.get('note') or ''}</p>
    {error}
    <table>
      <thead><tr><th>Title</th><th>Source</th><th>City</th><th>URL</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</body>
</html>"""


@router.get("/chroma", response_class=HTMLResponse)
def chroma_viewer() -> str:
    from app.rag.vector_store import collection_preview

    return _page(collection_preview())
