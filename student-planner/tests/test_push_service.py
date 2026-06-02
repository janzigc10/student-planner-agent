from unittest.mock import MagicMock, patch

from app.services.push_service import PushResult, send_push


def _make_subscription():
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/fake-token",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8p8REfWPU=",
            "auth": "tBHItJI5svbpC7-BnWW_IA==",
        },
    }


@patch("app.services.push_service.webpush")
def test_send_push_success(mock_webpush):
    mock_webpush.return_value = MagicMock(status_code=201)

    result = send_push(
        subscription=_make_subscription(),
        title="高等数学",
        body="10:00 @ 教学楼A301",
    )

    assert result.ok is True
    assert result.status_code == 201
    mock_webpush.assert_called_once()
    assert mock_webpush.call_args.kwargs["timeout"] == 8.0
    assert mock_webpush.call_args.kwargs["ttl"] == 60 * 60


@patch("app.services.push_service.webpush")
def test_send_push_expired_subscription(mock_webpush):
    from pywebpush import WebPushException

    response_mock = MagicMock()
    response_mock.status_code = 410
    mock_webpush.side_effect = WebPushException("Gone", response=response_mock)

    result = send_push(
        subscription=_make_subscription(),
        title="Test",
        body="Test body",
    )

    assert result.ok is False
    assert result.should_unsubscribe is True


@patch("app.services.push_service.webpush")
def test_send_push_other_failure(mock_webpush):
    from pywebpush import WebPushException

    response_mock = MagicMock()
    response_mock.status_code = 500
    mock_webpush.side_effect = WebPushException("Server error", response=response_mock)

    result = send_push(
        subscription=_make_subscription(),
        title="Test",
        body="Test body",
    )

    assert result.ok is False
    assert result.should_unsubscribe is False
    assert result.status_code == 500


def test_send_push_no_subscription():
    result = send_push(subscription=None, title="Test", body="Test body")
    assert result == PushResult(ok=False, error="No subscription")


@patch("app.services.push_service.webpush")
def test_send_push_generic_exception(mock_webpush):
    mock_webpush.side_effect = TimeoutError("push timed out")

    result = send_push(
        subscription=_make_subscription(),
        title="Test",
        body="Test body",
    )

    assert result.ok is False
    assert result.should_unsubscribe is False
    assert result.status_code == 0
    assert "timed out" in result.error
