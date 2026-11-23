"""Tour photos: JPG/PNG only, size limit, files on disk, order (form 4.6.2.1, field 18)."""
import os
import re
from pathlib import Path

import pytest

from app.config import settings
from app.models import Tour
from app.models.enums import TourStatus
from tests.factories import make_tour

URL = "/api/manager/tours"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def upload(client, headers, tour_id, *files):
    return client.post(f"{URL}/{tour_id}/images", headers=headers,
                       files=[("files", f) for f in files])


def files_on_disk(tour_id) -> list[Path]:
    folder = Path(settings.upload_dir) / "tours" / str(tour_id)
    return sorted(folder.iterdir()) if folder.exists() else []


@pytest.fixture()
def tour(db, manager):
    return make_tour(db, manager)


def test_upload_jpg_and_png_served_as_static(client, manager_headers, tour):
    response = upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg"),
                      ("b.png", PNG, "image/png"))
    assert response.status_code == 201, response.text
    images = response.json()
    assert [i["sort_order"] for i in images] == [0, 1]
    assert images[0]["url"].endswith(".jpg") and images[1]["url"].endswith(".png")
    assert "file_path" not in images[0]
    assert len(files_on_disk(tour.id)) == 2
    served = client.get(images[0]["url"])
    assert served.status_code == 200
    assert served.content == JPEG
    # The tour form shows the photos too
    assert len(client.get(f"{URL}/{tour.id}", headers=manager_headers).json()["images"]) == 2


def test_type_detected_from_content_not_name(client, manager_headers, tour):
    fake = ("photo.jpg", b"just some text, not an image", "image/jpeg")
    gif = ("anim.gif", b"GIF89a" + b"\x00" * 50, "image/gif")
    for file in (fake, gif):
        response = upload(client, manager_headers, tour.id, file)
        assert response.status_code == 422
        assert "JPG або PNG" in response.json()["detail"]
    assert files_on_disk(tour.id) == []


def test_bad_file_rejects_the_whole_upload(client, db, manager_headers, tour):
    response = upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg"),
                      ("b.txt", b"text", "text/plain"))
    assert response.status_code == 422
    assert files_on_disk(tour.id) == []      # the good file was removed too
    db.expire_all()
    assert db.get(Tour, tour.id).images == []


def test_size_limit(client, manager_headers, tour, monkeypatch):
    monkeypatch.setattr(settings, "max_image_mb", 1)
    big = JPEG + b"\x00" * (1024 * 1024)
    response = upload(client, manager_headers, tour.id, ("big.jpg", big, "image/jpeg"))
    assert response.status_code == 413
    assert "1 МБ" in response.json()["detail"]
    assert files_on_disk(tour.id) == []


def test_max_images_per_tour(client, manager_headers, tour, monkeypatch):
    monkeypatch.setattr(settings, "max_images_per_tour", 2)
    assert upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg")).status_code == 201
    response = upload(client, manager_headers, tour.id, ("b.jpg", JPEG, "image/jpeg"),
                      ("c.jpg", JPEG, "image/jpeg"))
    assert response.status_code == 422
    assert "не більше 2 фото" in response.json()["detail"]


def test_delete_image_removes_row_and_file(client, manager_headers, tour):
    images = upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg"),
                    ("b.png", PNG, "image/png")).json()
    response = client.delete(f"{URL}/{tour.id}/images/{images[0]['id']}", headers=manager_headers)
    assert response.status_code == 204
    assert [p.suffix for p in files_on_disk(tour.id)] == [".png"]
    assert client.get(images[0]["url"]).status_code == 404
    left = client.get(f"{URL}/{tour.id}", headers=manager_headers).json()["images"]
    assert [i["id"] for i in left] == [images[1]["id"]]
    again = client.delete(f"{URL}/{tour.id}/images/{images[0]['id']}", headers=manager_headers)
    assert again.status_code == 404


def test_reorder_images(client, db, manager, manager_headers, tour):
    ids = [i["id"] for i in upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg"),
                                   ("b.png", PNG, "image/png"), ("c.jpg", JPEG, "image/jpeg")).json()]
    new_order = [ids[2], ids[0], ids[1]]
    response = client.put(f"{URL}/{tour.id}/images/order", json={"image_ids": new_order},
                          headers=manager_headers)
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()] == new_order
    form = client.get(f"{URL}/{tour.id}", headers=manager_headers).json()
    assert [i["id"] for i in form["images"]] == new_order

    other = make_tour(db, manager)
    other_id = upload(client, manager_headers, other.id, ("x.jpg", JPEG, "image/jpeg")).json()[0]["id"]
    for wrong in ([ids[0], ids[1]], ids + [other_id], [ids[0], ids[0], ids[1]],
                  [ids[0], ids[1], other_id]):
        response = client.put(f"{URL}/{tour.id}/images/order", json={"image_ids": wrong},
                              headers=manager_headers)
        assert response.status_code == 422, wrong


def test_photos_of_active_tour_are_locked(client, db, manager, manager_headers, tour):
    image_id = upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg")).json()[0]["id"]
    db.get(Tour, tour.id).status = TourStatus.ACTIVE
    db.flush()
    assert upload(client, manager_headers, tour.id, ("b.jpg", JPEG, "image/jpeg")).status_code == 409
    assert client.delete(f"{URL}/{tour.id}/images/{image_id}",
                         headers=manager_headers).status_code == 409
    assert client.put(f"{URL}/{tour.id}/images/order", json={"image_ids": [image_id]},
                      headers=manager_headers).status_code == 409


def test_copy_duplicates_photo_files(client, manager_headers, tour):
    upload(client, manager_headers, tour.id, ("a.jpg", JPEG, "image/jpeg"), ("b.png", PNG, "image/png"))
    copy = client.post(f"{URL}/{tour.id}/copy", headers=manager_headers).json()
    assert len(copy["images"]) == 2
    assert len(files_on_disk(copy["id"])) == 2
    source_urls = {i["url"] for i in client.get(f"{URL}/{tour.id}", headers=manager_headers)
                   .json()["images"]}
    assert source_urls.isdisjoint(i["url"] for i in copy["images"])
    # deleting a photo of the copy keeps the source file
    client.delete(f"{URL}/{copy['id']}/images/{copy['images'][0]['id']}", headers=manager_headers)
    assert len(files_on_disk(tour.id)) == 2


@pytest.mark.parametrize("filename", ["../../x.png", "..\\..\\x.png", "/etc/x.png"])
def test_client_file_name_never_becomes_the_path(client, manager_headers, tour, tmp_path,
                                                monkeypatch, filename):
    """The server names the file itself (tours/<id>/<uuid>.png); a path in the uploaded
    name cannot write outside the upload folder."""
    uploads = tmp_path / "srv" / "uploads"
    monkeypatch.setattr(settings, "upload_dir", uploads)
    response = upload(client, manager_headers, tour.id, (filename, PNG, "image/png"))
    assert response.status_code == 201, response.text
    url = response.json()[0]["url"]
    assert re.fullmatch(rf"/uploads/tours/{tour.id}/[0-9a-f]{{32}}\.png", url), url
    written = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert written == [uploads / "tours" / str(tour.id) / url.rsplit("/", 1)[1]]


def test_upload_dir_is_the_test_folder():
    """Guard: tests must never write into the real backend/uploads."""
    assert "tour-test-uploads-" in os.fspath(settings.upload_dir)
