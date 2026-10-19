from pathlib import Path
from urllib.parse import urlparse, unquote

def uri_paths(uris):
    paths = []
    for uri in uris or []:
        parsed = urlparse(uri)
        if parsed.scheme == 'file' and parsed.netloc in {'', 'localhost'}:
            path = Path(unquote(parsed.path))
            if path.exists(): paths.append(path)
    return paths

