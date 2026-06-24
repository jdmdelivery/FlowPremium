"""Legal pages for AdSense compliance."""


def test_privacy_policy_page(client):
    resp = client.get("/privacy-policy")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Privacidad" in body or "Privacy" in body
    assert "AdSense" in body or "adsense" in body.lower() or "Google" in body


def test_terms_page(client):
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert resp.data


def test_contact_page(client):
    resp = client.get("/contact")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Contact" in body or "Contacto" in body


def test_footer_links_on_home(client):
    resp = client.get("/streaming/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "/privacy-policy" in body
    assert "/terms" in body
    assert "/contact" in body
