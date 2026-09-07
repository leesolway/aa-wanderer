"""
Wrapper around the requests library to remove boilerplate and direct requests to wanderer more efficiently
"""

import requests
from requests import Response

from allianceauth.services.hooks import get_extension_logger

DEFAULT_TIMEOUT = 5


logger = get_extension_logger(__name__)


class BadAPIKeyError(Exception):
    """Exception raised when a wrong API key is provided"""


def request(
    method: str,
    wanderer_base_url: str,
    url_path: str,
    json: dict | None = None,
    bearer_token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Response:
    """
    Sends a request of method type to a wanderer instance
    """
    logger.debug(
        "Sending %s request to %s / %s with json %s and bearer token %s",
        method,
        wanderer_base_url,
        url_path,
        json,
        bearer_token,
    )

    headers = create_header_dic_from_potential_bearer_token(bearer_token)

    r = requests.request(
        method,
        f"{wanderer_base_url}/api/{url_path}",
        json=json,
        headers=headers,
        timeout=timeout,
    )

    logger.debug("received code %d with text %s", r.status_code, r.text)

    raise_for_errors(r)

    return r


def get(
    wanderer_base_url: str,
    url_path: str,
    *,
    json: dict | None = None,
    bearer_token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Response:
    """
    Sends a GET request to a wanderer instance
    """
    return request(
        "GET", wanderer_base_url, url_path, json, bearer_token, timeout=timeout
    )


def post(
    wanderer_base_url: str,
    url_path: str,
    *,
    json: dict | None = None,
    bearer_token: str | None = None,
) -> Response:
    """
    Sends a POST request to a wanderer instance
    """
    return request("POST", wanderer_base_url, url_path, json, bearer_token)


def delete(
    wanderer_base_url: str,
    url_path: str,
    *,
    json: dict | None = None,
    bearer_token: str | None = None,
) -> Response:
    """
    Sends a DELETE request to a wanderer instance
    """
    return request("DELETE", wanderer_base_url, url_path, json, bearer_token)


def put(
    wanderer_base_url: str,
    url_path: str,
    *,
    json: dict | None = None,
    bearer_token: str | None = None,
) -> Response:
    """
    Sends a PUT request to a wanderer instance
    """
    return request("PUT", wanderer_base_url, url_path, json, bearer_token)


def create_header_dic_from_potential_bearer_token(
    bearer_token: str | None,
) -> dict | None:
    """
    If a bearer token is passed returns a headers dictionnary properly formatted
    Returns None otherwise
    """
    headers = None

    if bearer_token:
        headers = {"Authorization": f"Bearer {bearer_token}"}

    return headers


def raise_for_errors(response: Response):
    """
    Executes different tests that could raise errors from the response
    """

    if response.status_code == 401:
        raise BadAPIKeyError()

    response.raise_for_status()
