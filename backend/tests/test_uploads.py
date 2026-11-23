"""Only tour photos are public static files; anything else in the upload folder is not served."""
import shutil
from pathlib import Path

import pytest

from app.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
SECRET = b"secret: passport scan"


@pytest.fixture()
def private_files():
    """A tour photo plus files a future feature might store next to it (order documents)."""
    root = Path(settings.upload_dir)
    created = [root / "tours" / "static-test" / "photo.png", root / "secret.txt",
               root / "orders" / "1" / "voucher.pdf"]
    for path, content in zip(created, (PNG, SECRET, SECRET)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    yield
    shutil.rmtree(root / "tours" / "static-test", ignore_errors=True)
    shutil.rmtree(root / "orders", ignore_errors=True)
    (root / "secret.txt").unlink(missing_ok=True)


def test_tour_photos_are_served(client, private_files):
    response = client.get("/uploads/tours/static-test/photo.png")
    assert response.status_code == 200
    assert response.content == PNG


@pytest.mark.parametrize("url", [
    "/uploads/secret.txt",
    "/uploads/orders/1/voucher.pdf",
    "/uploads/tours/../secret.txt",          # normalised by the client to /uploads/secret.txt
    "/uploads/tours/%2e%2e/secret.txt",      # encoded dots reach the server as-is
    "/uploads/tours/..%2Fsecret.txt",
    "/uploads/tours/%2e%2e/orders/1/voucher.pdf",
])
def test_files_outside_tours_folder_are_not_served(client, private_files, url):
    response = client.get(url)
    assert response.status_code == 404, url
    assert SECRET not in response.content
