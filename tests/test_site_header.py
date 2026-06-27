"""Site header appears on streaming and auth pages."""


def test_streaming_index_has_site_header(client):
    resp = client.get("/streaming/")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'id="main-nav"' in html
    assert "StreamPremium" in html
    assert 'class="nav-link is-active"' in html or "is-active" in html
    assert "Métodos de pago" in html or "Payment" in html
    assert 'id="home-search"' in html


def test_login_has_site_header(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'id="main-nav"' in html
    assert "StreamPremium" in html
