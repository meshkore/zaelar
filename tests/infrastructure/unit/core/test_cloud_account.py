from nucleo import cloud_account


def test_is_cloud_account_false_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert cloud_account.is_cloud_account() is False
    assert cloud_account.my_user_id() == ""


def test_is_cloud_account_true_when_user_id_set(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    assert cloud_account.is_cloud_account() is True
    assert cloud_account.my_user_id() == "did:key:z6MkExample"


def test_is_cloud_account_false_when_blank(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "   ")
    assert cloud_account.is_cloud_account() is False
